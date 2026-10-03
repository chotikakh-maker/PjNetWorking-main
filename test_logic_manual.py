"""
สคริปต์ทดสอบ game logic แบบ manual (ไม่ผ่าน network เลย)
รันด้วย: py test_logic_manual.py
ลบไฟล์นี้ได้หลังยืนยันว่า logic ถูกต้อง หรือแปลงเป็น unittest ทีหลังก็ได้
"""

from server.game.card import Card
from server.game import rules
from server.game.room import Room


def test_calculate_score():
    cards = [Card("Spade", "7"), Card("Heart", "8")]  # 7+8=15 -> mod10 = 5
    assert rules.calculate_score(cards) == 5
    cards = [Card("Spade", "K"), Card("Heart", "Q")]  # 0+0=0
    assert rules.calculate_score(cards) == 0
    print("test_calculate_score OK")


def test_is_pok():
    pok9 = [Card("Spade", "9"), Card("Heart", "K")]  # 9+0=9
    pok8 = [Card("Spade", "8"), Card("Heart", "10")]  # 8+0=8
    not_pok = [Card("Spade", "5"), Card("Heart", "2")]  # 7 แต้ม ไม่ป๊อก

    assert rules.is_pok(pok9) == (True, 9)
    assert rules.is_pok(pok8) == (True, 8)
    assert rules.is_pok(not_pok) == (False, 7)
    print("test_is_pok OK")


def test_compare_pok9_beats_pok8():
    dealer = [Card("Spade", "8"), Card("Heart", "10")]  # pok8
    player = [Card("Club", "9"), Card("Diamond", "K")]  # pok9
    result = rules.compare(dealer, player)
    assert result["winner"] == "player"
    print("test_compare_pok9_beats_pok8 OK")


def test_compare_higher_score_wins():
    dealer = [Card("Spade", "3"), Card("Heart", "2")]  # 5
    player = [Card("Club", "6"), Card("Diamond", "2")]  # 8... wait not pok since need exactly first 2
    # 6+2=8 -> เป็นป๊อกจริง ลองเปลี่ยนให้ไม่ป๊อกแทน
    player = [Card("Club", "6"), Card("Diamond", "1".replace("1", "A"))]  # A=1 -> 6+1=7
    result = rules.compare(dealer, player)
    assert result["dealer"]["score"] == 5
    assert result["player"]["score"] == 7
    assert result["winner"] == "player"
    print("test_compare_higher_score_wins OK")


def test_compare_tie_dealer_wins():
    dealer = [Card("Spade", "3"), Card("Heart", "2")]  # 5
    player = [Card("Club", "4"), Card("Diamond", "A")]  # 5
    result = rules.compare(dealer, player)
    assert result["winner"] == "dealer"  # เสมอ = เจ้ามือชนะ
    print("test_compare_tie_dealer_wins OK")


def test_compare_bod_case():
    dealer = [Card("Spade", "10"), Card("Heart", "K")]  # 0 (บอด)
    player = [Card("Club", "2"), Card("Diamond", "A")]  # 3
    result = rules.compare(dealer, player)
    assert result["winner"] == "player"
    print("test_compare_bod_case OK")


def test_room_full_flow_no_pok():
    room = Room("test-room")
    room.add_player("conn-dealer", "เจ้ามือมด")
    room.add_player("conn-1", "ผู้เล่น1")
    room.add_player("conn-2", "ผู้เล่น2")

    room.start_round()
    assert room.state == "betting"

    # ผู้เล่นที่ไม่ใช่เจ้ามือต้องวางเดิมพันให้ครบก่อน ถึงจะแจกไพ่จริง (เข้า playing/reveal)
    for conn_id, player in list(room.players.items()):
        if not player.is_dealer:
            room.player_place_bet(conn_id, 10)

    assert room.state in ("playing", "reveal", "dealer_decision")

    # ถ้ายังอยู่ playing (ไม่ป๊อกหมด) ให้ผู้เล่นที่ยัง thinking เลือก stay ทีละคนจนจบ
    if room.state == "playing":
        for conn_id, player in list(room.players.items()):
            if player.status == "thinking":
                room.player_stay(conn_id)
    if room.state == "dealer_decision":
        room.dealer_manual_stay(room.get_dealer().connection_id)

    assert room.state == "reveal"
    summary = room.reveal_and_settle()
    assert "dealer" in summary
    assert "results" in summary
    assert len(summary["results"]) == 2  # ผู้เล่น 2 คน ไม่รวมเจ้ามือ
    print("test_room_full_flow_no_pok OK")
    print("  summary:", summary)


def test_reveal_and_settle_is_idempotent():
    # จำลอง race condition จริง: ws_server.py เรียก reveal_and_settle() จากหลาย handler
    # (place_bet/player_draw/player_stay) ทุกครั้งที่ state กลายเป็น reveal ถ้า action ของผู้เล่น
    # สองคนมาถึงพร้อมกัน handler ทั้งสองจะเห็น state==reveal และเรียกซ้ำได้ ต้องไม่หัก balance ซ้ำ
    room = Room("idempotent-room")
    room.add_player("conn-dealer", "เจ้ามือ")
    room.add_player("conn-1", "ผู้เล่น1")
    room.add_player("conn-2", "ผู้เล่น2")

    room.start_round()
    for conn_id, player in list(room.players.items()):
        if not player.is_dealer:
            room.player_place_bet(conn_id, 10)
    if room.state == "playing":
        for conn_id, player in list(room.players.items()):
            if player.status == "thinking":
                room.player_stay(conn_id)
    if room.state == "dealer_decision":
        dealer = room.get_dealer()
        room.dealer_manual_stay(dealer.connection_id)
    assert room.state == "reveal"

    first = room.reveal_and_settle()
    second = room.reveal_and_settle()
    assert first == second
    for conn_id, player in room.players.items():
        if not player.is_dealer:
            assert player.balance == first["results"][conn_id]["balance"]
    print("test_reveal_and_settle_is_idempotent OK")


def test_room_rejects_full():
    room = Room("small-room", max_players=2)
    room.add_player("c1", "A")
    room.add_player("c2", "B")
    try:
        room.add_player("c3", "C")
        assert False, "ควร raise ValueError เพราะห้องเต็ม"
    except ValueError:
        print("test_room_rejects_full OK")


if __name__ == "__main__":
    test_calculate_score()
    test_is_pok()
    test_compare_pok9_beats_pok8()
    test_compare_higher_score_wins()
    test_compare_tie_dealer_wins()
    test_compare_bod_case()
    test_room_full_flow_no_pok()
    test_reveal_and_settle_is_idempotent()
    test_room_rejects_full()
    print("\nALL TESTS PASSED")
