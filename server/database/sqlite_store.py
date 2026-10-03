"""Small SQLite persistence layer for the classroom/demo version.

No external database service is required.  The file is created in server/data/pokdeng.sqlite3.
The adapter intentionally keeps authentication lightweight: a browser-generated user id is the
account key and the display name can be changed from the client.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from threading import Lock


class SQLiteStore:
    def __init__(self, path: str | None = None, starting_coins: int = 300, daily_coin: int = 100, coin_cap: int = 500):
        self.path = Path(path or Path(__file__).resolve().parent / "data" / "pokdeng.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.starting_coins = starting_coins
        self.daily_coin = daily_coin
        self.coin_cap = coin_cap
        self._lock = Lock()
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock, self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    coins INTEGER NOT NULL,
                    last_claim TEXT,
                    games INTEGER NOT NULL DEFAULT 0,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    draws INTEGER NOT NULL DEFAULT 0,
                    net_profit INTEGER NOT NULL DEFAULT 0,
                    total_bet INTEGER NOT NULL DEFAULT 0,
                    current_streak INTEGER NOT NULL DEFAULT 0,
                    best_streak INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    room_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    dealer_name TEXT NOT NULL,
                    result TEXT NOT NULL,
                    bet INTEGER NOT NULL,
                    profit INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dealer_stats (
                    dealer_name TEXT PRIMARY KEY,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    draws INTEGER NOT NULL DEFAULT 0,
                    total_profit INTEGER NOT NULL DEFAULT 0,
                    decisions_draw INTEGER NOT NULL DEFAULT 0,
                    decisions_stand INTEGER NOT NULL DEFAULT 0
                );
                """
            )

    def ensure_user(self, user_id: str, display_name: str = "Player"):
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO users(user_id,display_name,coins) VALUES(?,?,?)",
                    (user_id, display_name[:20], self.starting_coins),
                )
            else:
                db.execute("UPDATE users SET display_name=? WHERE user_id=?", (display_name[:20], user_id))
            db.commit()
        return self.get_user(user_id)

    def get_user(self, user_id: str):
        with self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
            return dict(row) if row else None

    def claim_daily(self, user_id: str, display_name: str = "Player"):
        self.ensure_user(user_id, display_name)
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
            today = date.today().isoformat()
            if row["last_claim"] == today:
                return False, row["coins"]
            new_coins = min(self.coin_cap, row["coins"] + self.daily_coin)
            db.execute("UPDATE users SET coins=?,last_claim=? WHERE user_id=?", (new_coins, today, user_id))
            db.commit()
            return True, new_coins

    def get_balance(self, user_id: str):
        row = self.get_user(user_id)
        return row["coins"] if row else self.starting_coins

    def update_match(self, user_id, room_id, mode, dealer_name, result, bet, profit):
        if mode != "ranked":
            return
        self.ensure_user(user_id)
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
            games = row["games"] + 1
            wins = row["wins"] + (1 if result == "win" else 0)
            losses = row["losses"] + (1 if result == "loss" else 0)
            draws = row["draws"] + (1 if result == "draw" else 0)
            streak = row["current_streak"] + 1 if result == "win" else 0
            best = max(row["best_streak"], streak)
            db.execute(
                """UPDATE users SET coins=?,games=?,wins=?,losses=?,draws=?,net_profit=net_profit+?,
                   total_bet=total_bet+?,current_streak=?,best_streak=? WHERE user_id=?""",
                (max(0, row["coins"] + profit), games, wins, losses, draws, profit, bet, streak, best, user_id),
            )
            db.execute(
                "INSERT INTO matches(user_id,room_id,mode,dealer_name,result,bet,profit,created_at) VALUES(?,?,?,?,?,?,?,datetime('now'))",
                (user_id, room_id, mode, dealer_name, result, bet, profit),
            )
            db.commit()

    def sync_balance(self, user_id, balance):
        with self._lock, self._connect() as db:
            db.execute("UPDATE users SET coins=? WHERE user_id=?", (max(0, int(balance)), user_id))
            db.commit()

    def update_dealer(self, dealer_name, result, profit=0, decision=None):
        with self._lock, self._connect() as db:
            db.execute("INSERT OR IGNORE INTO dealer_stats(dealer_name) VALUES(?)", (dealer_name,))
            field = {"win": "wins", "loss": "losses", "draw": "draws"}.get(result)
            if field:
                db.execute(f"UPDATE dealer_stats SET {field}={field}+1,total_profit=total_profit+? WHERE dealer_name=?", (profit, dealer_name))
            if decision == "draw":
                db.execute("UPDATE dealer_stats SET decisions_draw=decisions_draw+1 WHERE dealer_name=?", (dealer_name,))
            elif decision == "stand":
                db.execute("UPDATE dealer_stats SET decisions_stand=decisions_stand+1 WHERE dealer_name=?", (dealer_name,))
            db.commit()

    def human_leaderboard(self, period="all"):
        if period == "all":
            with self._connect() as db:
                rows = db.execute("SELECT * FROM users ORDER BY coins DESC, net_profit DESC LIMIT 20").fetchall()
            out = []
            for r in rows:
                games = r["games"]
                out.append({
                    "user_id": r["user_id"], "name": r["display_name"], "coins": r["coins"],
                    "net_profit": r["net_profit"], "win_rate": round(r["wins"] / games * 100, 2) if games else 0,
                    "games": games, "best_streak": r["best_streak"], "average_profit": round(r["net_profit"] / games, 2) if games else 0,
                })
            return out
        days = 0 if period == "today" else 7
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        with self._connect() as db:
            rows = db.execute("""SELECT u.user_id,u.display_name,u.coins,
                COUNT(m.id) games, COALESCE(SUM(CASE WHEN m.result='win' THEN 1 ELSE 0 END),0) wins,
                COALESCE(SUM(CASE WHEN m.result='loss' THEN 1 ELSE 0 END),0) losses,
                COALESCE(SUM(m.profit),0) net_profit
                FROM users u LEFT JOIN matches m ON m.user_id=u.user_id AND date(m.created_at)>=date(?)
                GROUP BY u.user_id ORDER BY net_profit DESC, coins DESC LIMIT 20""", (cutoff,)).fetchall()
        return [{
            "user_id": r["user_id"], "name": r["display_name"], "coins": r["coins"], "net_profit": r["net_profit"],
            "win_rate": round(r["wins"] / r["games"] * 100, 2) if r["games"] else 0, "games": r["games"],
            "best_streak": 0, "average_profit": round(r["net_profit"] / r["games"], 2) if r["games"] else 0,
        } for r in rows]

    def dealer_leaderboard(self):
        with self._connect() as db:
            rows = db.execute("SELECT * FROM dealer_stats ORDER BY (wins*1.0)/NULLIF(wins+losses+draws,0) DESC").fetchall()
        out = []
        for r in rows:
            total = r["wins"] + r["losses"] + r["draws"]
            out.append({
                "dealer_name": r["dealer_name"], "win_rate": round(r["wins"] / total * 100, 2) if total else 0,
                "loss_rate": round(r["losses"] / total * 100, 2) if total else 0,
                "draw_rate": round(r["draws"] / total * 100, 2) if total else 0,
                "total_games": total, "average_profit": round(r["total_profit"] / total, 2) if total else 0,
                "draw_decisions": r["decisions_draw"], "stand_decisions": r["decisions_stand"],
            })
        return out
