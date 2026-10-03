import asyncio,json,uuid,websockets
WS_URL="ws://localhost:8765"
async def recv_until(ws,wanted):
    while True:
        m=json.loads(await asyncio.wait_for(ws.recv(),timeout=8))
        if m["type"]=="error": raise AssertionError(m)
        if m["type"] in wanted:return m
async def connect_join(name,room):
    ws=await websockets.connect(WS_URL); uid=str(uuid.uuid4())
    await ws.send(json.dumps({"type":"login","user_id":uid,"player_name":name})); await recv_until(ws,{"session"})
    await ws.send(json.dumps({"type":"join_room","room_id":room,"player_name":name})); cid=(await recv_until(ws,{"room_joined"}))["connection_id"]
    return ws,cid
async def play(ws,cid,name,action,results,dealer=False):
    acted=False;bet=False
    try:
        while True:
            m=json.loads(await asyncio.wait_for(ws.recv(),timeout=10))
            if m["type"]=="round_result": results[name]=m["data"];return
            if m["type"]!="game_state":continue
            st=m["data"]; me=next(p for p in st["players"] if p["connection_id"]==cid)
            if st["state"]=="betting" and not me["is_dealer"] and not bet:
                bet=True; await ws.send(json.dumps({"type":"place_bet","amount":10,"round_number":st["round_number"],"action_id":str(uuid.uuid4())}))
            if st["state"]=="playing" and not me["is_dealer"] and me["status"]=="thinking" and not acted:
                acted=True; await ws.send(json.dumps({"type":action,"round_number":st["round_number"],"action_id":str(uuid.uuid4())}))
            if st["state"]=="dealer_decision" and me["is_dealer"] and not acted:
                acted=True; await ws.send(json.dumps({"type":"dealer_stay","round_number":st["round_number"],"action_id":str(uuid.uuid4())}))
    finally: await ws.close()
async def main():
    room="e2e-"+uuid.uuid4().hex[:8]; results={}
    dealer=await websockets.connect(WS_URL); uid=str(uuid.uuid4())
    await dealer.send(json.dumps({"type":"login","user_id":uid,"player_name":"Dealer"})); await recv_until(dealer,{"session"})
    await dealer.send(json.dumps({"type":"create_room","room_id":room,"player_name":"Dealer","stake":100,"dealer_strategy":"human","mode":"practice","max_players":3})); did=(await recv_until(dealer,{"room_joined"}))["connection_id"]
    alice=await connect_join("Alice",room); bob=await connect_join("Bob",room)
    await dealer.send(json.dumps({"type":"start_round"}))
    await asyncio.gather(play(dealer,did,"Dealer","player_stay",results,True),play(alice[0],alice[1],"Alice","player_draw",results),play(bob[0],bob[1],"Bob","player_stay",results))
    assert set(results)=={"Dealer","Alice","Bob"};print("E2E TEST PASSED — human dealer room completed")
if __name__ == "__main__":
    asyncio.run(main())
