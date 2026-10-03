"""WebSocket transport for the authoritative multi-room game server."""
import asyncio
import json
import time
import uuid

import websockets
from websockets.asyncio.server import serve

from server.database.sqlite_store import SQLiteStore
from server.game.room import RoomManager
from server.network import protocol

DB = SQLiteStore()
room_manager = RoomManager(DB)
connections = {}
# token -> {room_id, old_connection_id, user_id, expires_at}
sessions = {}
room_tasks = {}

TUTORIAL = {
    "title": "วิธีเล่นป๊อกเด้ง Online",
    "steps": [
        {"title": "1. เลือกโหมด", "text": "Practice เล่นฝึกได้โดยไม่กระทบ Ranking ส่วน Ranked ใช้ Virtual Coin และผลแพ้ชนะจะบันทึกสถิติ"},
        {"title": "2. เข้าห้อง", "text": "สร้างห้องหรือเลือกห้องที่มีอยู่ ห้องหนึ่งรองรับ 2–5 คนรวมเจ้ามือ"},
        {"title": "3. วางเดิมพัน", "text": "เมื่อเจ้ามือเริ่มรอบ ผู้เล่นวางเดิมพันให้ครบ ระบบจึงแจกไพ่"},
        {"title": "4. ดูไพ่และตัดสินใจ", "text": "ไพ่ของคนอื่นจะถูกปิดไว้ คุณเลือก จั่วเพิ่ม เพื่อรับใบที่ 3 หรือ อยู่ เพื่อหยุด"},
        {"title": "5. เจ้่ามือตัดสินใจ", "text": "ถ้าเป็น AI จะรอให้ผู้เล่นทุกคนตัดสินใจก่อน แล้ว strategy จะเลือก DRAW หรือ STAND พร้อมเหตุผล"},
        {"title": "6. เปิดไพ่และคิดผล", "text": "Server เป็นผู้คำนวณแต้ม ป๊อก เด้ง ไพ่พิเศษ และเงินรางวัลทั้งหมด"},
        {"title": "7. กติกาโบนัสของโปรเจกต์", "text": "ไพ่ 2 ใบ: ดอกเดียวกันหรือแต้มหน้าเดียวกัน = Double x2; ไพ่ 3 ใบ: ตอง x5, สเตรทฟลัช x3, แต้ม 8/9 จาก 3 ใบ x2"},
        {"title": "8. Fair Dealing", "text": "ก่อนแจก Server ส่ง SHA-256 commitment ของสำรับ หลังจบรอบจะเปิด seed + deck order เพื่อให้ตรวจสอบย้อนหลังได้"},
    ],
}


def _profile(user_id, name):
    user = DB.ensure_user(user_id, name)
    return {
        "user_id": user_id, "name": user["display_name"], "coins": user["coins"],
        "games": user["games"], "wins": user["wins"], "losses": user["losses"], "draws": user["draws"],
        "net_profit": user["net_profit"], "win_rate": round(user["wins"] / user["games"] * 100, 2) if user["games"] else 0,
        "best_streak": user["best_streak"], "last_claim": user["last_claim"],
    }


async def handler(websocket):
    connection_id = str(uuid.uuid4())
    connections[websocket] = {"connection_id": connection_id, "room_id": None, "user_id": None, "session_token": None}
    await send_to(websocket, protocol.make_message(protocol.ROOM_LIST, data=room_manager.list_rooms_summary()))
    try:
        async for raw_message in websocket:
            await handle_message(websocket, raw_message)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        await handle_disconnect(websocket)


async def handle_message(websocket, raw_message):
    try:
        data = json.loads(raw_message)
    except json.JSONDecodeError:
        await send_to(websocket, protocol.make_error("ข้อความไม่ใช่ JSON ที่ถูกต้อง"))
        return
    msg_type = data.get("type")
    info = connections[websocket]
    try:
        handlers = {
            protocol.LOGIN: on_login,
            protocol.CLAIM_DAILY: on_claim_daily,
            protocol.GET_LEADERBOARDS: on_leaderboards,
            protocol.GET_TUTORIAL: on_tutorial,
            protocol.RESUME_SESSION: on_resume_session,
            protocol.CREATE_ROOM: on_create_room,
            protocol.JOIN_ROOM: on_join_room,
            protocol.START_ROUND: on_start_round,
            protocol.PLACE_BET: on_place_bet,
            protocol.PLAYER_DRAW: on_player_draw,
            protocol.PLAYER_STAY: on_player_stay,
            protocol.DEALER_DRAW: on_dealer_draw,
            protocol.DEALER_STAY: on_dealer_stay,
            protocol.LEAVE_ROOM: on_leave_room,
            protocol.PING: on_ping,
        }
        handler_fn = handlers.get(msg_type)
        if handler_fn is None:
            raise ValueError(f"ไม่รู้จัก message type: {msg_type}")
        await handler_fn(websocket, info, data)
    except ValueError as exc:
        await send_to(websocket, protocol.make_error(str(exc)))


async def on_login(websocket, info, data):
    name = str(data.get("player_name", "")).strip()[:20]
    user_id = str(data.get("user_id", "")).strip()
    if not name or not user_id:
        raise ValueError("ต้องระบุชื่อและ user id")
    info["user_id"] = user_id
    DB.ensure_user(user_id, name)
    token = str(uuid.uuid4())
    info["session_token"] = token
    sessions[token] = {"room_id": None, "old_connection_id": info["connection_id"], "user_id": user_id, "expires_at": time.time() + 600}
    await send_to(websocket, protocol.make_message(protocol.SESSION, token=token, profile=_profile(user_id, name)))


async def on_claim_daily(websocket, info, data):
    if not info.get("user_id"):
        raise ValueError("กรุณาเข้าสู่ระบบก่อน")
    claimed, coins = DB.claim_daily(info["user_id"], str(data.get("player_name", "Player")))
    await send_to(websocket, protocol.make_message(protocol.PROFILE, data=_profile(info["user_id"], str(data.get("player_name", "Player"))), claimed=claimed, reward=100 if claimed else 0, coins=coins))


async def on_leaderboards(websocket, info, data):
    await send_to(websocket, protocol.make_message(protocol.LEADERBOARDS, data={"human": DB.human_leaderboard(data.get("period", "all")), "dealer": DB.dealer_leaderboard()}))


async def on_tutorial(websocket, info, data):
    await send_to(websocket, protocol.make_message(protocol.TUTORIAL, data=TUTORIAL))


async def on_resume_session(websocket, info, data):
    token = str(data.get("token", ""))
    session = sessions.get(token)
    if not session or session["expires_at"] < time.time() or not session.get("room_id"):
        raise ValueError("Session หมดอายุ กรุณาเข้าห้องใหม่")
    room = room_manager.get_room(session["room_id"])
    if room is None:
        raise ValueError("ห้องเดิมถูกปิดแล้ว")
    player = room.reconnect_player(session["old_connection_id"], info["connection_id"])
    info.update({"room_id": room.room_id, "user_id": player.user_id, "session_token": token})
    session["old_connection_id"] = info["connection_id"]
    session["expires_at"] = time.time() + 600
    await send_to(websocket, protocol.make_message(protocol.ROOM_JOINED, connection_id=info["connection_id"], room_id=room.room_id, resumed=True))
    await broadcast_game_state(room)


async def on_create_room(websocket, info, data):
    if not info.get("user_id"):
        raise ValueError("กรุณาเข้าสู่ระบบก่อน")
    room_id = str(data.get("room_id", "")).strip()
    player_name = str(data.get("player_name", "")).strip()[:20]
    mode = str(data.get("mode", "practice"))
    dealer_strategy = data.get("dealer_strategy", "human")
    max_players = int(data.get("max_players", 5))
    stake = int(data.get("stake", 1000))
    if mode == "ranked" and DB.get_balance(info["user_id"]) <= 0:
        raise ValueError("เหรียญไม่พอ กรุณารับ Daily Coin ก่อน")
    room = room_manager.create_room(room_id, max_players=max_players, stake=stake, dealer_strategy=dealer_strategy, mode=mode)
    player = room.add_player(info["connection_id"], player_name, info["user_id"])
    info["room_id"] = room_id
    token = info.get("session_token")
    if token:
        sessions[token] = {"room_id": room_id, "old_connection_id": info["connection_id"], "user_id": player.user_id, "expires_at": time.time() + 600}
    await send_to(websocket, protocol.make_message(protocol.ROOM_JOINED, connection_id=info["connection_id"], room_id=room_id))
    await broadcast_game_state(room)
    await broadcast_room_list()
    schedule_room_timeout(room)


async def on_join_room(websocket, info, data):
    if not info.get("user_id"):
        raise ValueError("กรุณาเข้าสู่ระบบก่อน")
    room_id = str(data.get("room_id", "")).strip()
    player_name = str(data.get("player_name", "")).strip()[:20]
    room = room_manager.get_room(room_id)
    if room is None:
        raise ValueError("ไม่พบห้องนี้")
    if room.mode == "ranked" and DB.get_balance(info["user_id"]) <= 0:
        raise ValueError("เหรียญไม่พอสำหรับ Ranked")
    player = room.add_player(info["connection_id"], player_name, info["user_id"])
    info["room_id"] = room_id
    token = info.get("session_token")
    if token:
        sessions[token] = {"room_id": room_id, "old_connection_id": info["connection_id"], "user_id": player.user_id, "expires_at": time.time() + 600}
    await send_to(websocket, protocol.make_message(protocol.ROOM_JOINED, connection_id=info["connection_id"], room_id=room_id))
    await broadcast_game_state(room)
    await broadcast_room_list()


async def on_start_round(websocket, info, data):
    room = _get_room_or_raise(info)
    room.start_round()
    await broadcast_game_state(room)
    schedule_room_timeout(room)


async def on_place_bet(websocket, info, data):
    room = _get_room_or_raise(info)
    room.player_place_bet(info["connection_id"], int(data.get("amount")), data.get("action_id"), data.get("round_number"))
    await after_action(room)


async def on_player_draw(websocket, info, data):
    room = _get_room_or_raise(info)
    room.player_draw_card(info["connection_id"], data.get("action_id"), data.get("round_number"))
    await after_action(room)


async def on_player_stay(websocket, info, data):
    room = _get_room_or_raise(info)
    room.player_stay(info["connection_id"], data.get("action_id"), data.get("round_number"))
    await after_action(room)


async def on_dealer_draw(websocket, info, data):
    room = _get_room_or_raise(info)
    room.dealer_manual_draw(info["connection_id"], data.get("action_id"), data.get("round_number"))
    await after_action(room)


async def on_dealer_stay(websocket, info, data):
    room = _get_room_or_raise(info)
    room.dealer_manual_stay(info["connection_id"], data.get("action_id"), data.get("round_number"))
    await after_action(room)


async def after_action(room):
    await broadcast_game_state(room)
    if room.state == "reveal":
        await broadcast_round_result(room)
    else:
        schedule_room_timeout(room)


async def on_leave_room(websocket, info, data):
    room = _get_room_or_raise(info)
    room_id = room.room_id
    connection_id = info["connection_id"]
    token = info.get("session_token")

    room.remove_player(connection_id)
    info["room_id"] = None

    # Intentional leave must cancel room-resume state. Otherwise a refresh/reconnect
    # can silently put the player back into the room they explicitly left.
    if token and token in sessions:
        sessions[token]["room_id"] = None
        sessions[token]["old_connection_id"] = None
        sessions[token]["expires_at"] = time.time() + 600

    task = room_tasks.pop(room_id, None)
    if task:
        task.cancel()

    if room.players:
        await broadcast_game_state(room)
    else:
        room_manager.remove_room(room_id)

    await broadcast_room_list()
    await send_to(websocket, protocol.make_message(protocol.LEFT_ROOM, room_id=room_id))


def _get_room_or_raise(info):
    room = room_manager.get_room(info.get("room_id")) if info.get("room_id") else None
    if room is None:
        raise ValueError("คุณยังไม่ได้เข้าห้อง")
    return room


async def handle_disconnect(websocket):
    info = connections.pop(websocket, None)
    if info is None:
        return
    room = room_manager.get_room(info.get("room_id")) if info.get("room_id") else None
    token = info.get("session_token")
    if room and token:
        room.disconnect_player(info["connection_id"])
        sessions[token] = {"room_id": room.room_id, "old_connection_id": info["connection_id"], "user_id": info.get("user_id"), "expires_at": time.time() + 120}
        await broadcast_game_state(room)
    elif room:
        room.remove_player(info["connection_id"])
        await broadcast_game_state(room)
    await broadcast_room_list()


async def send_to(websocket, message_dict):
    await websocket.send(json.dumps(message_dict, ensure_ascii=False))


async def broadcast_game_state(room):
    targets = _room_websockets(room)
    if not targets:
        return
    await asyncio.gather(*(ws.send(json.dumps(protocol.make_message(protocol.GAME_STATE, data=room.to_dict_for(connections[ws]["connection_id"])), ensure_ascii=False)) for ws in targets), return_exceptions=True)


async def broadcast_round_result(room):
    summary = room.reveal_and_settle()
    await _broadcast_to_room(room, protocol.make_message(protocol.ROUND_RESULT, data=summary))


async def _broadcast_to_room(room, message_dict):
    payload = json.dumps(message_dict, ensure_ascii=False)
    targets = _room_websockets(room)
    if targets:
        await asyncio.gather(*(ws.send(payload) for ws in targets), return_exceptions=True)


def _room_websockets(room):
    return [ws for ws, info in connections.items() if info.get("room_id") == room.room_id]


async def broadcast_room_list():
    payload = json.dumps(protocol.make_message(protocol.ROOM_LIST, data=room_manager.list_rooms_summary()), ensure_ascii=False)
    targets = [ws for ws, info in connections.items() if not info.get("room_id")]
    if targets:
        await asyncio.gather(*(ws.send(payload) for ws in targets), return_exceptions=True)


def schedule_room_timeout(room):
    old = room_tasks.pop(room.room_id, None)
    if old:
        old.cancel()
    if room.phase_deadline is None:
        return
    room_tasks[room.room_id] = asyncio.create_task(_timeout_worker(room))


async def _timeout_worker(room):
    try:
        delay = max(0.1, room.phase_deadline - time.time())
        await asyncio.sleep(delay)
        if room.phase_deadline and time.time() >= room.phase_deadline and room.state in ("betting", "playing", "dealer_decision"):
            room.timeout_auto_action()
            await broadcast_game_state(room)
            if room.state == "reveal":
                await broadcast_round_result(room)
            else:
                schedule_room_timeout(room)
    except asyncio.CancelledError:
        return


async def on_ping(websocket, info, data):
    await send_to(websocket, protocol.make_message(protocol.PONG, ts=time.time()))


async def _session_cleanup_loop():
    while True:
        await asyncio.sleep(10)
        now = time.time()
        expired = [token for token, s in sessions.items() if s["expires_at"] < now]
        for token in expired:
            s = sessions.pop(token, None)
            if not s or not s.get("room_id"):
                continue
            room = room_manager.get_room(s["room_id"])
            if room and s.get("old_connection_id") in room.players and not room.players[s["old_connection_id"]].connected:
                room.remove_player(s["old_connection_id"])
                if not room.players:
                    room_manager.remove_room(room.room_id)


async def run_server(host, port):
    cleanup_task = asyncio.create_task(_session_cleanup_loop())
    try:
        async with serve(handler, host, port):
            await asyncio.get_running_loop().create_future()
    finally:
        cleanup_task.cancel()
