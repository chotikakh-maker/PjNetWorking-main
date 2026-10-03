"""Authoritative game room and multi-room manager."""
from __future__ import annotations

import time
from collections import OrderedDict

from server.game import game_state, rules
from server.game.card import Deck
from server.game.dealer_strategy import create_strategy
from server.game.deck_verifier import DeckVerifier
from server.game.player import (
    Player, STATUS_DRAWN, STATUS_OUT_OF_MONEY, STATUS_POK, STATUS_STAY,
    STATUS_THINKING, STATUS_WAITING, STATUS_DISCONNECTED,
)

MIN_PLAYERS_TO_START = 2  # total seats, including dealer
ACTION_TTL = 120


class Room:
    def __init__(self, room_id, max_players=5, stake=100, dealer_strategy=None, mode="practice", db=None):
        self.room_id = room_id
        self.max_players = max(2, min(max_players, 8))
        self.stake = stake
        self.mode = mode if mode in ("practice", "ranked") else "practice"
        self.db = db
        self.dealer_strategy = create_strategy(dealer_strategy)
        self.dealer_strategy_key = dealer_strategy or "human"
        self.players = OrderedDict()
        self.deck = None
        self.deck_verifier = None
        self._committed_deck_order = []
        self.state = game_state.WAITING
        self.round_number = 0
        self.round_started_at = None
        self.phase_deadline = None
        self._round_summary = None
        self._processed_actions = OrderedDict()
        self.dealer_decision = None
        self.last_dealer_reason = ""
        self.history = []

    def _remember_action(self, player, action_id):
        if not action_id:
            return
        if action_id in self._processed_actions:
            raise ValueError("คำสั่งนี้ถูกประมวลผลไปแล้ว")
        self._processed_actions[action_id] = time.time()
        while len(self._processed_actions) > 300:
            self._processed_actions.popitem(last=False)
        player.last_action_id = action_id

    def _validate_phase(self, expected, round_number=None):
        if self.state != expected:
            raise ValueError(f"ตอนนี้ไม่ใช่ช่วง {expected}")
        if round_number is not None and int(round_number) != self.round_number:
            raise ValueError("คำสั่งนี้เป็นของรอบเก่าแล้ว กรุณารอ state ล่าสุด")

    def add_player(self, connection_id, name, user_id=None):
        if len(self.players) >= self.max_players:
            raise ValueError("ห้องเต็มแล้ว")
        is_dealer = len(self.players) == 0
        player = Player(connection_id, name, is_dealer=is_dealer, user_id=user_id)
        if self.mode == "ranked" and self.db and user_id:
            player.balance = self.db.get_balance(user_id)
        else:
            player.balance = self.stake
        self.players[connection_id] = player
        return player

    def reconnect_player(self, old_connection_id, new_connection_id):
        player = self.players.get(old_connection_id)
        if player is None:
            raise ValueError("ไม่พบ session สำหรับ reconnect")
        self.players.pop(old_connection_id)
        player.connection_id = new_connection_id
        player.connected = True
        self.players[new_connection_id] = player
        return player

    def disconnect_player(self, connection_id):
        player = self.players.get(connection_id)
        if player:
            player.connected = False
        return player

    def remove_player(self, connection_id):
        player = self.players.pop(connection_id, None)
        if player and player.is_dealer and self.players:
            new_dealer = next(iter(self.players.values()))
            new_dealer.is_dealer = True

    def get_dealer(self):
        return next((p for p in self.players.values() if p.is_dealer), None)

    def get_non_dealer_players(self):
        return [p for p in self.players.values() if not p.is_dealer]

    def get_active_bettors(self):
        return [p for p in self.get_non_dealer_players() if p.status != STATUS_OUT_OF_MONEY]

    def start_round(self):
        if self.state not in (game_state.WAITING, game_state.REVEAL, game_state.SETTLEMENT):
            raise ValueError("ยังเริ่มรอบใหม่ไม่ได้ กรุณารอรอบปัจจุบันจบ")
        if len(self.players) < MIN_PLAYERS_TO_START:
            raise ValueError("ต้องมีอย่างน้อยเจ้ามือและผู้เล่น 1 คน")
        for player in self.players.values():
            player.reset_for_new_round()
        self._round_summary = None
        self.deck = None
        self.deck_verifier = None
        self._committed_deck_order = []
        self.dealer_decision = None
        self.last_dealer_reason = ""
        self.round_number += 1
        self.round_started_at = time.time()
        self.phase_deadline = time.time() + 45
        self.state = game_state.BETTING

    def player_place_bet(self, connection_id, amount, action_id=None, round_number=None):
        self._validate_phase(game_state.BETTING, round_number)
        player = self.players.get(connection_id)
        if not player or not player.connected:
            raise ValueError("ไม่พบผู้เล่นที่เชื่อมต่ออยู่")
        self._remember_action(player, action_id)
        if player.is_dealer:
            raise ValueError("เจ้ามือไม่ต้องวางเดิมพัน")
        if player.status == STATUS_OUT_OF_MONEY:
            raise ValueError("เงินหมดแล้ว")
        if player.has_bet:
            raise ValueError("วางเดิมพันไปแล้ว")
        if amount <= 0 or amount > player.balance:
            raise ValueError("จำนวนเดิมพันไม่ถูกต้อง")
        player.place_bet(amount)
        self._deal_cards_if_ready()

    def auto_bet_missing(self):
        if self.state != game_state.BETTING:
            return
        for player in self.get_active_bettors():
            if not player.has_bet:
                amount = min(10, player.balance)
                if amount > 0:
                    player.place_bet(amount)
        self._deal_cards_if_ready()

    def _deal_cards_if_ready(self):
        active = self.get_active_bettors()
        if active and all(p.has_bet for p in active):
            self._deal_cards()

    def _deal_cards(self):
        self.deck = Deck()
        self.deck_verifier = DeckVerifier()
        deck_order = [f"{card.suit}:{card.rank}" for card in self.deck.cards]
        self._committed_deck_order = deck_order.copy()
        self.deck_verifier.generate_commitment(deck_order)
        self.state = game_state.DEALING
        self.phase_deadline = time.time() + 35

        for player in self.players.values():
            if player.status == STATUS_OUT_OF_MONEY or not player.connected:
                continue
            player.receive_card(self.deck.draw())
            player.receive_card(self.deck.draw())
            pok, _ = rules.is_pok(player.hand)
            player.status = STATUS_POK if pok else STATUS_THINKING

        if self.all_players_done():
            self._enter_dealer_decision_or_reveal()
        else:
            self.state = game_state.PLAYING
            self.phase_deadline = time.time() + 30

    def player_draw_card(self, connection_id, action_id=None, round_number=None):
        self._validate_phase(game_state.PLAYING, round_number)
        player = self.players.get(connection_id)
        if not player or not player.connected:
            raise ValueError("ไม่พบผู้เล่นที่เชื่อมต่ออยู่")
        self._remember_action(player, action_id)
        if player.is_dealer:
            raise ValueError("เจ้ามือ AI จะตัดสินใจเอง")
        if player.status != STATUS_THINKING:
            raise ValueError("ผู้เล่นคนนี้ตัดสินใจไปแล้ว หรือป๊อกไปแล้ว")
        player.receive_card(self.deck.draw())
        player.status = STATUS_DRAWN
        self._advance_state_if_ready()

    def player_stay(self, connection_id, action_id=None, round_number=None):
        self._validate_phase(game_state.PLAYING, round_number)
        player = self.players.get(connection_id)
        if not player or not player.connected:
            raise ValueError("ไม่พบผู้เล่นที่เชื่อมต่ออยู่")
        self._remember_action(player, action_id)
        if player.is_dealer and self.dealer_strategy is None:
            player.status = STATUS_STAY
        elif player.is_dealer:
            raise ValueError("เจ้ามือ AI จะตัดสินใจเอง")
        elif player.status != STATUS_THINKING:
            raise ValueError("ผู้เล่นคนนี้ตัดสินใจไปแล้ว หรือป๊อกไปแล้ว")
        else:
            player.status = STATUS_STAY
        self._advance_state_if_ready()

    def dealer_manual_draw(self, connection_id, action_id=None, round_number=None):
        self._validate_phase(game_state.DEALER_DECISION, round_number)
        dealer = self.get_dealer()
        if not dealer or dealer.connection_id != connection_id or self.dealer_strategy is not None:
            raise ValueError("ไม่ใช่ตาเจ้ามือผู้เล่น")
        self._remember_action(dealer, action_id)
        dealer.receive_card(self.deck.draw())
        dealer.status = STATUS_DRAWN
        self.dealer_decision = "draw"
        self.state = game_state.REVEAL

    def dealer_manual_stay(self, connection_id, action_id=None, round_number=None):
        self._validate_phase(game_state.DEALER_DECISION, round_number)
        dealer = self.get_dealer()
        if not dealer or dealer.connection_id != connection_id or self.dealer_strategy is not None:
            raise ValueError("ไม่ใช่ตาเจ้ามือผู้เล่น")
        self._remember_action(dealer, action_id)
        dealer.status = STATUS_STAY
        self.dealer_decision = "stand"
        self.state = game_state.REVEAL

    def all_players_done(self):
        done = (STATUS_POK, STATUS_DRAWN, STATUS_STAY, STATUS_OUT_OF_MONEY, STATUS_DISCONNECTED)
        humans = self.get_non_dealer_players()
        return bool(humans) and all(p.status in done for p in humans if p.connected or p.status != STATUS_DISCONNECTED)

    def _all_non_dealer_players_done(self):
        humans = self.get_non_dealer_players()
        done = (STATUS_POK, STATUS_DRAWN, STATUS_STAY, STATUS_OUT_OF_MONEY, STATUS_DISCONNECTED)
        return bool(humans) and all(p.status in done for p in humans)

    def _advance_state_if_ready(self):
        if self._all_non_dealer_players_done():
            self._enter_dealer_decision_or_reveal()

    def _enter_dealer_decision_or_reveal(self):
        dealer = self.get_dealer()
        if dealer is None:
            raise ValueError("ห้องนี้ไม่มีเจ้ามือ")
        if dealer.status == STATUS_POK:
            self.state = game_state.REVEAL
            return
        if self.dealer_strategy is None:
            self.state = game_state.DEALER_DECISION
            self.phase_deadline = time.time() + 15
            return
        self.state = game_state.DEALER_DECISION
        self.phase_deadline = time.time() + 2
        self._run_ai_dealer()

    def _run_ai_dealer(self):
        if self.dealer_strategy is None or self.state != game_state.DEALER_DECISION:
            return
        dealer = self.get_dealer()
        if dealer is None:
            return
        public_players = [{
            "connection_id": p.connection_id,
            "is_dealer": False,
            "status": p.status,
            "drew_3rd_card": len(p.hand) >= 3,
        } for p in self.get_non_dealer_players()]
        dealer_score = rules.calculate_score(dealer.hand)
        should_draw = self.dealer_strategy.should_draw(dealer.hand, dealer_score, {"players": public_players})
        self.dealer_decision = "draw" if should_draw else "stand"
        self.last_dealer_reason = self.dealer_strategy.explain(dealer.hand, dealer_score, {"players": public_players}) if hasattr(self.dealer_strategy, "explain") else "strategy rule"
        if should_draw:
            dealer.receive_card(self.deck.draw())
            dealer.status = STATUS_DRAWN
        else:
            dealer.status = STATUS_STAY
        self.state = game_state.REVEAL

    def timeout_auto_action(self):
        if self.state == game_state.BETTING:
            self.auto_bet_missing()
            return
        if self.state == game_state.PLAYING:
            for p in self.get_non_dealer_players():
                if p.status == STATUS_THINKING:
                    p.status = STATUS_STAY
            self._advance_state_if_ready()
            return
        if self.state == game_state.DEALER_DECISION:
            dealer = self.get_dealer()
            if self.dealer_strategy is not None:
                self._run_ai_dealer()
            elif dealer:
                dealer.status = STATUS_STAY
                self.dealer_decision = "stand"
                self.state = game_state.REVEAL

    def reveal_and_settle(self):
        if self._round_summary is not None:
            return self._round_summary
        if self.state != game_state.REVEAL:
            raise ValueError("ยังไม่ถึงขั้นตอนเปิดไพ่")
        dealer = self.get_dealer()
        if dealer is None:
            raise ValueError("ห้องนี้ยังไม่มีเจ้ามือ")
        results = {}
        for player in self.get_non_dealer_players():
            if player.status == STATUS_OUT_OF_MONEY or not player.has_bet:
                continue
            result = rules.compare(dealer.hand, player.hand)
            bet = player.current_bet
            multiplier = result["multiplier"]
            delta = bet * multiplier if result["winner"] == "player" else -bet * multiplier
            player.balance = max(0, player.balance + delta)
            dealer.balance = max(0, dealer.balance - delta)
            if player.balance <= 0:
                player.status = STATUS_OUT_OF_MONEY
            outcome = "win" if result["winner"] == "player" else "loss"
            result["hand"] = [card.to_dict() for card in player.hand]
            result["bet"] = bet
            result["profit"] = delta
            result["balance"] = player.balance
            results[player.connection_id] = result
            if self.mode == "ranked" and self.db:
                self.db.update_match(player.user_id, self.room_id, self.mode, self.dealer_display_name(), outcome, bet, delta)
            dealer_outcome = "loss" if outcome == "win" else "win"
            if self.db:
                self.db.update_dealer(self.dealer_display_name(), dealer_outcome, -delta)
                if self.mode == "ranked" and dealer.user_id and self.dealer_strategy is None:
                    self.db.update_match(dealer.user_id, self.room_id, self.mode, self.dealer_display_name(), dealer_outcome, bet, -delta)

        if self.db and self.dealer_decision in ("draw", "stand"):
            self.db.update_dealer(self.dealer_display_name(), None, 0, self.dealer_decision)

        self.state = game_state.REVEAL
        self._round_summary = {
            "round_number": self.round_number,
            "mode": self.mode,
            "dealer": dealer.to_dict(reveal_cards=True),
            "dealer_strategy": self.dealer_display_name(),
            "dealer_decision": self.dealer_decision,
            "dealer_reason": self.last_dealer_reason,
            "results": results,
            "fairness": {
                "commitment": self.deck_verifier.deck_hash if self.deck_verifier else None,
                "reveal_seed": self.deck_verifier.get_reveal_data() if self.deck_verifier else None,
                "deck_order": list(self._committed_deck_order),
            },
        }
        self.history.append(self._round_summary)
        if len(self.history) > 20:
            self.history.pop(0)
        return self._round_summary

    def dealer_display_name(self):
        return self.dealer_strategy.name if self.dealer_strategy else "Human Dealer"

    def to_dict_for(self, viewer_connection_id):
        players_data = []
        for seat_index, player in enumerate(self.players.values(), start=1):
            reveal = player.connection_id == viewer_connection_id
            data = player.to_dict(reveal_cards=reveal)
            data["seat"] = seat_index
            players_data.append(data)
        return {
            "room_id": self.room_id,
            "state": self.state,
            "round_number": self.round_number,
            "phase_deadline": self.phase_deadline,
            "mode": self.mode,
            "players": players_data,
            "dealer_strategy": self.dealer_display_name(),
            "dealer_decision": self.dealer_decision,
            "dealer_reason": self.last_dealer_reason,
            "deck_commitment": self.deck_verifier.deck_hash if self.deck_verifier else None,
        }


class RoomManager:
    def __init__(self, db=None):
        self.rooms = {}
        self.db = db

    def create_room(self, room_id, max_players=5, stake=100, dealer_strategy=None, mode="practice"):
        room_id = room_id.strip()
        if not room_id or len(room_id) > 20:
            raise ValueError("ชื่อห้องต้องมี 1-20 ตัวอักษร")
        if room_id in self.rooms:
            raise ValueError("ชื่อห้องนี้มีคนใช้แล้ว")
        room = Room(room_id, max_players=max_players, stake=stake, dealer_strategy=dealer_strategy, mode=mode, db=self.db)
        self.rooms[room_id] = room
        return room

    def get_room(self, room_id):
        return self.rooms.get(room_id)

    def remove_room(self, room_id):
        self.rooms.pop(room_id, None)

    def list_rooms_summary(self):
        return [{
            "room_id": r.room_id, "player_count": len(r.players), "max_players": r.max_players,
            "stake": r.stake, "state": r.state, "mode": r.mode, "dealer_strategy": r.dealer_display_name()
        } for r in self.rooms.values()]
