"""Commit/reveal helper for demonstrating deck-order transparency.

The commitment is SHA-256(secret_seed + canonical deck order). The seed is kept
private until the round is over, then clients can recompute the hash.
"""
import hashlib
import os


class DeckVerifier:
    def __init__(self, secret_seed=None):
        self.secret_seed = secret_seed or os.urandom(16).hex()
        self.deck_hash = None

    @staticmethod
    def canonical_cards(deck_cards):
        return ",".join(deck_cards)

    def generate_commitment(self, deck_cards):
        data = f"{self.secret_seed}|{self.canonical_cards(deck_cards)}"
        self.deck_hash = hashlib.sha256(data.encode("utf-8")).hexdigest()
        return self.deck_hash

    def get_reveal_data(self):
        return self.secret_seed

    @staticmethod
    def verify(deck_cards, secret_seed, expected_hash):
        data = f"{secret_seed}|{DeckVerifier.canonical_cards(deck_cards)}"
        actual = hashlib.sha256(data.encode("utf-8")).hexdigest()
        return actual == expected_hash
