import websocket, json

def on_message(ws, msg):
    print("Received:", msg)
    ws.close()

def on_open(ws):
    ws.send(json.dumps({
        "assets_ids": ["76851224858465557854630513877491303486407309517666177092008299165931449376969"],
        "type": "market",
        "initial_dump": True,
        "custom_feature_enabled": False
    }))

ws = websocket.WebSocketApp("wss://ws-subscriptions-clob.polymarket.com/ws/market", on_open=on_open, on_message=on_message)
ws.run_forever()
