"""Dealer decision strategies.

The Smart Student Dealer exposes a deterministic explanation string so the strategy can be
shown during a demo and measured in simulation.
"""
import random


class BaseDealerStrategy:
    def __init__(self, name):
        self.name = name

    def should_draw(self, dealer_cards, dealer_score, public_state):
        raise NotImplementedError

    def explain(self, dealer_cards, dealer_score, public_state):
        return "No explanation provided."


class RandomDealer(BaseDealerStrategy):
    def __init__(self):
        super().__init__("Random Dealer")

    def should_draw(self, dealer_cards, dealer_score, public_state):
        return random.choice([True, False])

    def explain(self, dealer_cards, dealer_score, public_state):
        return "Random baseline: สุ่ม DRAW/STAND เพื่อใช้เป็น baseline"


class SimpleRuleDealer(BaseDealerStrategy):
    def __init__(self):
        super().__init__("Simple Rule Dealer")

    def should_draw(self, dealer_cards, dealer_score, public_state):
        return dealer_score < 4

    def explain(self, dealer_cards, dealer_score, public_state):
        return f"Simple rule: แต้ม {dealer_score} < 4 จึง DRAW" if dealer_score < 4 else f"Simple rule: แต้ม {dealer_score} >= 4 จึง STAND"


class SmartStudentDealer(BaseDealerStrategy):
    def __init__(self):
        super().__init__("Smart Student Dealer")

    def should_draw(self, dealer_cards, dealer_score, public_state):
        players = public_state.get("players", [])
        active = [p for p in players if p.get("status") != "out_of_money"]
        drew = sum(1 for p in active if p.get("drew_3rd_card", False))
        ratio = drew / len(active) if active else 0
        if dealer_score <= 5:
            return True
        if dealer_score >= 7:
            return False
        return ratio >= 0.75

    def explain(self, dealer_cards, dealer_score, public_state):
        players = public_state.get("players", [])
        active = [p for p in players if p.get("status") != "out_of_money"]
        drew = sum(1 for p in active if p.get("drew_3rd_card", False))
        ratio = drew / len(active) if active else 0
        if dealer_score <= 5:
            return f"Smart: แต้ม {dealer_score} ยังต่ำ จึง DRAW เพื่อเพิ่ม expected score"
        if dealer_score >= 7:
            return f"Smart: แต้มสูง {dealer_score} จึง STAND ลดความเสี่ยง"
        return f"Smart: แต้ม 6 และผู้เล่นจั่วใบ 3 = {drew}/{len(active)} ({ratio:.0%}); ถ้า >=75% จึง DRAW"


STRATEGY_FACTORIES = {"random": RandomDealer, "simple": SimpleRuleDealer, "smart": SmartStudentDealer}


def create_strategy(name):
    if name in (None, "", "human"):
        return None
    try:
        return STRATEGY_FACTORIES[name.lower()]()
    except KeyError as exc:
        raise ValueError(f"ไม่รู้จัก dealer strategy: {name}") from exc
