"""Regression tests for the Gemini additions and their integration with game logic."""
import hashlib

from server.game.card import Card
from server.game.dealer_strategy import RandomDealer, SimpleRuleDealer, SmartStudentDealer
from server.game.deck_verifier import DeckVerifier
from server.game.room import Room
from server.database.sqlite_store import SQLiteStore


def test_reveal_requires_reveal_state():
    room = Room("state-guard")
    room.add_player("d", "Dealer")
    room.add_player("p", "Player")
    try:
        room.reveal_and_settle()
        assert False, "reveal should reject calls outside reveal state"
    except ValueError:
        pass
    print("test_reveal_requires_reveal_state OK")


def test_deck_commit_reveal():
    cards = ["Spade:A", "Heart:10", "Club:9"]
    verifier = DeckVerifier(secret_seed="fixed-seed")
    commitment = verifier.generate_commitment(cards)
    expected = hashlib.sha256(b"fixed-seed|Spade:A,Heart:10,Club:9").hexdigest()
    assert commitment == expected
    assert DeckVerifier.verify(cards, "fixed-seed", commitment)
    assert not DeckVerifier.verify(cards + ["Diamond:2"], "fixed-seed", commitment)
    print("test_deck_commit_reveal OK")


def test_dealer_strategies():
    assert SimpleRuleDealer().should_draw([], 3, {"players": []}) is True
    assert SimpleRuleDealer().should_draw([], 4, {"players": []}) is False
    assert SmartStudentDealer().should_draw([], 6, {"players": []}) is False
    assert SmartStudentDealer().should_draw([], 3, {"players": []}) is True
    state = {"players": [
        {"is_dealer": False, "drew_3rd_card": True},
        {"is_dealer": False, "drew_3rd_card": True},
        {"is_dealer": False, "drew_3rd_card": False},
    ]}
    assert SmartStudentDealer().should_draw([], 5, state) is True
    print("test_dealer_strategies OK")


def test_ai_room_reaches_reveal_without_manual_dealer_action():
    room = Room("ai-test", max_players=3, stake=100, dealer_strategy="simple")
    dealer = room.add_player("d", "AI Dealer")
    p1 = room.add_player("p1", "A")
    p2 = room.add_player("p2", "B")
    room.start_round()
    room.player_place_bet("p1", 10)
    room.player_place_bet("p2", 10)
    assert room.state in ("playing", "reveal")
    # Both human players stay; if the initial deal already produced all pok,
    # the room can legitimately be in reveal immediately.
    if room.state == "playing":
        if p1.status == "thinking":
            room.player_stay("p1")
        if p2.status == "thinking":
            room.player_stay("p2")
    assert room.state == "reveal"
    summary = room.reveal_and_settle()
    assert summary["fairness"]["commitment"]
    assert summary["fairness"]["reveal_seed"]
    assert DeckVerifier.verify(
        summary["fairness"]["deck_order"],
        summary["fairness"]["reveal_seed"],
        summary["fairness"]["commitment"],
    )
    print("test_ai_room_reaches_reveal_without_manual_dealer_action OK")


def test_database_mock(tmp_path):
    db = SQLiteStore(str(tmp_path / "test.sqlite3"), starting_coins=100, daily_coin=100, coin_cap=500)
    claimed, coins = db.claim_daily("u1", "Tester")
    assert claimed and coins == 200
    claimed_again, coins_again = db.claim_daily("u1", "Tester")
    assert not claimed_again and coins_again == 200
    db.update_match("u1", "r1", "ranked", "Simple Rule Dealer", "loss", 10, -10)
    db.update_dealer("Simple Rule Dealer", "win", 10, "draw")
    assert db.get_user("u1")["coins"] == 190
    assert db.human_leaderboard()[0]["games"] == 1
    assert db.dealer_leaderboard()[0]["total_games"] == 1
    print("test_database_mock OK")


if __name__ == "__main__":
    test_reveal_requires_reveal_state()
    test_deck_commit_reveal()
    test_dealer_strategies()
    test_ai_room_reaches_reveal_without_manual_dealer_action()
    test_database_mock()
    print("\nFEATURE TESTS PASSED")
