from server.database.sqlite_store import SQLiteStore
from server.game.card import Card
from server.game import rules
from server.game.room import Room


def test_special_hands():
    pair = rules.get_hand_result([Card("Spade", "7"), Card("Heart", "7")])
    assert pair["hand_type"] == "double" and pair["multiplier"] == 2
    trips = rules.get_hand_result([Card("Spade", "7"), Card("Heart", "7"), Card("Club", "7")])
    assert trips["hand_type"] == "three_of_a_kind" and trips["multiplier"] == 5
    sf = rules.get_hand_result([Card("Spade", "4"), Card("Spade", "5"), Card("Spade", "6")])
    assert sf["hand_type"] == "straight_flush" and sf["multiplier"] == 3


def test_human_dealer_state_machine():
    room = Room("human", max_players=3, stake=100)
    dealer = room.add_player("d", "Dealer")
    room.add_player("p1", "A")
    room.add_player("p2", "B")
    room.start_round()
    room.player_place_bet("p1", 10)
    room.player_place_bet("p2", 10)
    if room.state == "playing":
        for p in list(room.get_non_dealer_players()):
            if p.status == "thinking": room.player_stay(p.connection_id)
    if room.state == "dealer_decision":
        room.dealer_manual_stay(dealer.connection_id)
    assert room.state == "reveal"


def test_ranked_sqlite_daily_and_leaderboard(tmp_path):
    db = SQLiteStore(str(tmp_path / "db.sqlite3"), starting_coins=300, daily_coin=100, coin_cap=500)
    claimed, coins = db.claim_daily("u", "Tester")
    assert claimed and coins == 400
    claimed2, coins2 = db.claim_daily("u", "Tester")
    assert not claimed2 and coins2 == 400
    db.update_match("u", "r", "ranked", "Smart Student Dealer", "win", 50, 50)
    rows = db.human_leaderboard()
    assert rows[0]["games"] == 1 and rows[0]["net_profit"] == 50


def test_duplicate_action_rejected():
    room = Room("dup", max_players=2, stake=100)
    room.add_player("d", "Dealer")
    room.add_player("p", "Player")
    room.start_round(); room.player_place_bet("p", 10)
    if room.state == "playing":
        p = room.players["p"]
        if p.status == "thinking":
            room.player_stay("p", action_id="same")
            try:
                room.player_stay("p", action_id="same")
                assert False
            except ValueError:
                pass


def test_practice_does_not_touch_ranked_db(tmp_path):
    db = SQLiteStore(str(tmp_path / "db.sqlite3"), starting_coins=300)
    room = Room("practice", max_players=2, stake=100, mode="practice", db=db)
    room.add_player("d", "Dealer", "u")
    room.add_player("p", "Player", "u2")
    assert db.get_user("u") is None


if __name__ == "__main__":
    test_special_hands(); test_human_dealer_state_machine(); print("enhanced feature tests OK")
