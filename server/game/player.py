"""Player model with stable user/session identity and per-round state."""
STATUS_WAITING = "waiting"
STATUS_THINKING = "thinking"
STATUS_POK = "pok"
STATUS_STAY = "stay"
STATUS_DRAWN = "drawn"
STATUS_OUT_OF_MONEY = "out_of_money"
STATUS_DISCONNECTED = "disconnected"


class Player:
    def __init__(self, connection_id, name, is_dealer=False, user_id=None):
        self.connection_id = connection_id
        self.user_id = user_id or connection_id
        self.name = name
        self.is_dealer = is_dealer
        self.hand = []
        self.status = STATUS_WAITING
        self.balance = 0
        self.current_bet = 0
        self.has_bet = False
        self.connected = True
        self.last_action_id = None
        self.session_token = None

    def reset_for_new_round(self):
        self.hand = []
        self.current_bet = 0
        self.has_bet = False
        if self.status != STATUS_OUT_OF_MONEY:
            self.status = STATUS_WAITING

    def place_bet(self, amount):
        self.current_bet = amount
        self.has_bet = True

    def receive_card(self, card):
        self.hand.append(card)

    def to_dict(self, reveal_cards=False):
        data = {
            "connection_id": self.connection_id,
            "user_id": self.user_id,
            "name": self.name,
            "is_dealer": self.is_dealer,
            "status": self.status,
            "card_count": len(self.hand),
            "balance": self.balance,
            "current_bet": self.current_bet,
            "has_bet": self.has_bet,
            "connected": self.connected,
        }
        if reveal_cards:
            data["hand"] = [card.to_dict() for card in self.hand]
        return data
