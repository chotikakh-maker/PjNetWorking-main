WAITING = "waiting"
BETTING = "betting"
DEALING = "dealing"
PLAYING = "playing"
DEALER_DECISION = "dealer_decision"
REVEAL = "reveal"
SETTLEMENT = "settlement"

_VALID_TRANSITIONS = {
    WAITING: [BETTING],
    BETTING: [DEALING],
    DEALING: [PLAYING, DEALER_DECISION, REVEAL],
    PLAYING: [DEALER_DECISION, REVEAL],
    DEALER_DECISION: [REVEAL],
    REVEAL: [SETTLEMENT, BETTING, WAITING],
    SETTLEMENT: [BETTING, WAITING],
}


def can_transition(current_state, next_state):
    return next_state in _VALID_TRANSITIONS.get(current_state, [])
