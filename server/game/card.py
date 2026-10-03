"""
card.py
-------
นิยาม class Card (ไพ่ 1 ใบ) และ Deck (สำรับไพ่ 52 ใบ)
ไฟล์นี้ไม่รู้จัก websocket หรือ room เลย เป็น "หน่วยเล็กที่สุด" ของเกม
"""

import random

# ดอกไพ่ 4 ดอก และอันดับไพ่ 13 อันดับ (มาตรฐานสำรับ 52 ใบ)
SUITS = ["Spade", "Heart", "Diamond", "Club"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


class Card:
    """ไพ่ 1 ใบ เก็บดอก (suit) และอันดับ (rank)"""

    def __init__(self, suit, rank):
        self.suit = suit
        self.rank = rank

    @property
    def point(self):
        """
        คำนวณแต้มของไพ่ 1 ใบตามกติกาป๊อกเด้ง
        A = 1, เลข 2-9 = ตามหน้าไพ่, 10/J/Q/K = 0
        """
        if self.rank == "A":
            return 1
        if self.rank in ("10", "J", "Q", "K"):
            return 0
        return int(self.rank)

    def to_dict(self):
        """แปลงเป็น dict เพื่อส่งผ่าน JSON ให้ client"""
        return {"suit": self.suit, "rank": self.rank}

    def __repr__(self):
        return f"{self.rank}{self.suit[0]}"


class Deck:
    """สำรับไพ่ 52 ใบ สร้างใหม่และสับทุกครั้งที่เริ่มรอบใหม่"""

    def __init__(self):
        self.cards = [Card(suit, rank) for suit in SUITS for rank in RANKS]
        self.shuffle()

    def shuffle(self):
        random.shuffle(self.cards)

    def draw(self):
        """จั่วไพ่ 1 ใบจากด้านบนสำรับ (เอาออกจาก list แล้วคืนค่า)"""
        return self.cards.pop()
