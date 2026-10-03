import random
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from collections import Counter
from server.game.dealer_strategy import RandomDealer, SimpleRuleDealer, SmartStudentDealer


def simulate_dealer_match(dealer_strategy, iterations=10000):
    wins = losses = draws = 0
    profit = 0
    decisions = Counter()
    for _ in range(iterations):
        deck = [min(x, 10) for x in range(1, 14)] * 4
        random.shuffle(deck)
        player_score = (deck.pop() + deck.pop()) % 10
        dealer_score = (deck.pop() + deck.pop()) % 10
        if player_score < 5:
            player_score = (player_score + deck.pop()) % 10
            player_third = True
        else:
            player_third = False
        public_state = {"players": [{"drew_3rd_card": player_third, "status": "drawn" if player_third else "stay"}]}
        should_draw = dealer_strategy.should_draw([], dealer_score, public_state)
        decisions["DRAW" if should_draw else "STAND"] += 1
        if should_draw:
            dealer_score = (dealer_score + deck.pop()) % 10
        if dealer_score > player_score:
            wins += 1; profit += 1
        elif dealer_score < player_score:
            losses += 1; profit -= 1
        else:
            draws += 1
    print(f"[{dealer_strategy.name}] Dealer Win {wins/iterations*100:.2f}% | Loss {losses/iterations*100:.2f}% | Draw {draws/iterations*100:.2f}% | Avg P/L {profit/iterations:.4f} | Decisions {dict(decisions)}")
    return {"win_rate": wins/iterations*100, "loss_rate": losses/iterations*100, "draw_rate": draws/iterations*100, "average_profit": profit/iterations, "decisions": dict(decisions)}


if __name__ == "__main__":
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    print(f"Dealer Strategy Evaluation — {iterations:,} rounds\n")
    for strategy in (RandomDealer(), SimpleRuleDealer(), SmartStudentDealer()):
        simulate_dealer_match(strategy, iterations)
