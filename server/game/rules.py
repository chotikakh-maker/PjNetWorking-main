"""Server-side Pok Deng rules.

The project uses a documented classroom ruleset so the result is deterministic and testable:
- A=1, 2-9 face value, 10/J/Q/K=0; score is modulo 10.
- Pok 8/9 is recognised from the first two cards.
- Two-card "double" = same suit OR same rank, multiplier 2.
- Three-card specials: three-of-a-kind x5, straight-flush x3, and three-card 8/9 x2.
- If multiple specials apply, the highest multiplier wins.
- Equal ranked hands go to the dealer.
"""


def calculate_score(cards):
    return sum(card.point for card in cards) % 10


def is_pok(cards):
    if len(cards) != 2:
        return False, calculate_score(cards)
    score = calculate_score(cards)
    return score in (8, 9), score


def _is_straight(cards):
    if len(cards) != 3:
        return False
    values = {"A": 1, "J": 11, "Q": 12, "K": 13}
    nums = sorted(values.get(c.rank, int(c.rank) if c.rank.isdigit() else 0) for c in cards)
    return nums == list(range(nums[0], nums[0] + 3)) or nums == [1, 2, 3]


def get_hand_result(cards):
    score = calculate_score(cards)
    pok, _ = is_pok(cards) if len(cards) == 2 else (False, score)
    hand_type = "pok" if pok else "normal"
    multiplier = 1

    if len(cards) == 2:
        same_suit = cards[0].suit == cards[1].suit
        same_rank = cards[0].rank == cards[1].rank
        if same_suit or same_rank:
            hand_type = "double"
            multiplier = 2
    elif len(cards) == 3:
        ranks = [c.rank for c in cards]
        suits = [c.suit for c in cards]
        if len(set(ranks)) == 1:
            hand_type, multiplier = "three_of_a_kind", 5
        elif len(set(suits)) == 1 and _is_straight(cards):
            hand_type, multiplier = "straight_flush", 3
        elif score in (8, 9):
            hand_type, multiplier = "three_card_pok", 2

    return {"score": score, "is_pok": pok, "hand_type": hand_type, "multiplier": multiplier}


def _rank_value(hand_result):
    if hand_result["is_pok"]:
        return 100 + hand_result["score"]
    return hand_result["score"]


def compare(dealer_cards, player_cards):
    dealer_result = get_hand_result(dealer_cards)
    player_result = get_hand_result(player_cards)
    dealer_rank = _rank_value(dealer_result)
    player_rank = _rank_value(player_result)
    winner = "player" if player_rank > dealer_rank else "dealer"
    # multiplier is applied to the losing side's relevant special.  If both have a special,
    # use the player's multiplier when the player wins, otherwise dealer's multiplier.
    applied_multiplier = player_result["multiplier"] if winner == "player" else dealer_result["multiplier"]
    return {"winner": winner, "dealer": dealer_result, "player": player_result, "multiplier": applied_multiplier}
