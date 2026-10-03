import asyncio, json, uuid, websockets
WS_URL="ws://localhost:8765"
async def recv_until(ws,wanted):
    while True:
        m=json.loads(await asyncio.wait_for(ws.recv(),timeout=8))
        if m["type"]=="error": raise AssertionError(m)
        if m["type"] in wanted: return m
async def connect_join(name,room):
    ws=await websockets.connect(WS_URL); uid=str(uuid.uuid4())
    await ws.send(json.dumps({"type":"login","user_id":uid,"player_name":name})); await recv_until(ws,{"session"})
    await ws.send(json.dumps({"type":"join_room","room_id":room,"player_name":name})); my_id=(await recv_until(ws,{"room_joined"}))["connection_id"]
    return ws,my_id
async def play(ws,my_id,name,results):
    acted=False; bet=False
    try:
        while True:
            m=json.loads(await asyncio.wait_for(ws.recv(),timeout=10))
            if m["type"]=="round_result": results[name]=m["data"]; return
            if m["type"]!="game_state": continue
            st=m["data"]; me=next(p for p in st["players"] if p["connection_id"]==my_id)
            if st["state"]=="betting" and not me["is_dealer"] and not bet:
                bet=True; await ws.send(json.dumps({"type":"place_bet","amount":10,"round_number":st["round_number"],"action_id":str(uuid.uuid4())}))
            if st["state"]=="playing" and not me["is_dealer"] and me["status"]=="thinking" and not acted:
                acted=True; await ws.send(json.dumps({"type":"player_stay","round_number":st["round_number"],"action_id":str(uuid.uuid4())}))
    finally: await ws.close()
async def main():
    results={}; room="ai-e2e-"+uuid.uuid4().hex[:8]
    creator=await websockets.connect(WS_URL); uid=str(uuid.uuid4())
    await creator.send(json.dumps({"type":"login","user_id":uid,"player_name":"AI Dealer"})); await recv_until(creator,{"session"})
    await creator.send(json.dumps({"type":"create_room","room_id":room,"player_name":"AI Dealer","stake":100,"dealer_strategy":"smart","mode":"practice","max_players":3})); creator_id=(await recv_until(creator,{"room_joined"}))["connection_id"]
    a=await connect_join("Alice",room); b=await connect_join("Bob",room)
    await creator.send(json.dumps({"type":"start_round"}))
    await asyncio.gather(play(creator,creator_id,"AI Dealer",results),play(a[0],a[1],"Alice",results),play(b[0],b[1],"Bob",results))
    assert set(results)=={"AI Dealer","Alice","Bob"}; assert results["Alice"]["fairness"]["commitment"]
    print("AI E2E TEST PASSED")
if __name__ == "__main__":
    asyncio.run(main())
