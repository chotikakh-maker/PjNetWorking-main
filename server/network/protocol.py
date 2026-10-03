CREATE_ROOM = "create_room"
JOIN_ROOM = "join_room"
START_ROUND = "start_round"
PLACE_BET = "place_bet"
PLAYER_DRAW = "player_draw"
PLAYER_STAY = "player_stay"
DEALER_DRAW = "dealer_draw"
DEALER_STAY = "dealer_stay"
LOGIN = "login"
CLAIM_DAILY = "claim_daily"
GET_LEADERBOARDS = "get_leaderboards"
RESUME_SESSION = "resume_session"
LEAVE_ROOM = "leave_room"
GET_TUTORIAL = "get_tutorial"
PING = "ping"

ROOM_JOINED = "room_joined"
LEFT_ROOM = "left_room"
GAME_STATE = "game_state"
ROUND_RESULT = "round_result"
ERROR = "error"
ROOM_LIST = "room_list"
PROFILE = "profile"
LEADERBOARDS = "leaderboards"
SESSION = "session"
TUTORIAL = "tutorial"
PONG = "pong"


def make_message(msg_type, **kwargs):
    message = {"type": msg_type}
    message.update(kwargs)
    return message


def make_error(text):
    return make_message(ERROR, message=text)
