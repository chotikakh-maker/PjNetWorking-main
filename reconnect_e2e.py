import asyncio, json, uuid, websockets
WS='ws://localhost:8765'
async def recv(ws, typ, timeout=5):
    while True:
        m=json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
        if m['type']=='error': raise AssertionError(m)
        if m['type']==typ: return m
async def main():
    room='reconnect-'+uuid.uuid4().hex[:6]; uid=str(uuid.uuid4())
    a=await websockets.connect(WS); await a.send(json.dumps({'type':'login','user_id':uid,'player_name':'Reconnecter'})); sess=(await recv(a,'session'))['token']
    await a.send(json.dumps({'type':'create_room','room_id':room,'player_name':'Reconnecter','stake':100,'dealer_strategy':'smart','mode':'practice','max_players':2})); await recv(a,'room_joined')
    b=await websockets.connect(WS); await b.send(json.dumps({'type':'login','user_id':str(uuid.uuid4()),'player_name':'Friend'})); await recv(b,'session')
    await b.send(json.dumps({'type':'join_room','room_id':room,'player_name':'Friend'})); await recv(b,'room_joined')
    # Drain creator state and start
    await a.send(json.dumps({'type':'start_round'}));
    # wait until betting then bet from b
    got=False
    while not got:
        m=json.loads(await a.recv())
        if m['type']=='game_state' and m['data']['state']=='betting': got=True
    await b.send(json.dumps({'type':'place_bet','amount':10,'round_number':1,'action_id':str(uuid.uuid4())}))
    await asyncio.sleep(.2); await a.close()
    c=await websockets.connect(WS); await c.send(json.dumps({'type':'resume_session','token':sess})); joined=await recv(c,'room_joined'); assert joined['resumed']
    msg=await recv(c,'game_state'); state=msg['data']; assert state['room_id']==room and any(p['connected'] for p in state['players'])
    print('RECONNECT E2E PASSED')
    await b.close(); await c.close()
asyncio.run(main())
