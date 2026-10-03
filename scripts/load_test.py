"""Concurrent multi-room smoke test.
Usage: python scripts/load_test.py 10 3
"""
import asyncio, json, sys, time, uuid
import websockets

WS_URL="ws://localhost:8765"

async def recv_until(ws, wanted):
    while True:
        msg=json.loads(await asyncio.wait_for(ws.recv(), timeout=8))
        if msg["type"]=="error": raise RuntimeError(msg["message"])
        if msg["type"] in wanted: return msg

async def room_flow(index, players):
    room=f"load-{index}-{uuid.uuid4().hex[:4]}"
    sockets=[]
    async def connect_player(i):
        ws=await websockets.connect(WS_URL); sockets.append(ws)
        uid=str(uuid.uuid4()); name=f"L{index}-{i}"
        await ws.send(json.dumps({"type":"login","user_id":uid,"player_name":name}))
        await recv_until(ws,{"session"})
        if i==0:
            await ws.send(json.dumps({"type":"create_room","room_id":room,"player_name":name,"stake":100,"dealer_strategy":"smart","mode":"practice","max_players":players}))
        else:
            await ws.send(json.dumps({"type":"join_room","room_id":room,"player_name":name}))
        joined=await recv_until(ws,{"room_joined"})
        return ws,joined["connection_id"],name
    try:
        creator=await connect_player(0)
        others=await asyncio.gather(*(connect_player(i) for i in range(1,players)))
        all_players=[creator,*others]
        async def play(i, item):
            ws,my_id,name=item
            started=False; bet=False; acted=False
            while True:
                msg=json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                if msg["type"]=="round_result": return True
                if msg["type"]=="error": raise RuntimeError(msg["message"])
                if msg["type"]!="game_state": continue
                state=msg["data"]
                me=next(p for p in state["players"] if p["connection_id"]==my_id)
                if i==0 and not started and len(state["players"])==players:
                    started=True; await ws.send(json.dumps({"type":"start_round"}))
                if state["state"]=="betting" and not me["is_dealer"] and not bet:
                    bet=True; await ws.send(json.dumps({"type":"place_bet","amount":10,"round_number":state["round_number"],"action_id":str(uuid.uuid4())}))
                if state["state"]=="playing" and not me["is_dealer"] and me["status"]=="thinking" and not acted:
                    acted=True; await ws.send(json.dumps({"type":"player_stay","round_number":state["round_number"],"action_id":str(uuid.uuid4())}))
        results=await asyncio.gather(*(play(i,item) for i,item in enumerate(all_players)))
        return all(results)
    finally:
        for ws in sockets:
            await ws.close()

async def main():
    rooms=int(sys.argv[1]) if len(sys.argv)>1 else 5; players=int(sys.argv[2]) if len(sys.argv)>2 else 3
    t=time.perf_counter(); results=await asyncio.gather(*(room_flow(i,players) for i in range(rooms)), return_exceptions=True); elapsed=time.perf_counter()-t
    ok=sum(r is True for r in results); print(f"Concurrent rooms: {rooms} | players/room: {players} | completed: {ok}/{rooms} | elapsed: {elapsed:.2f}s")
    for i,r in enumerate(results):
        if isinstance(r,Exception): print(f"room {i}: {r}")

if __name__=="__main__": asyncio.run(main())
