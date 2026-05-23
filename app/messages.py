async def handle_send(username, msg, websocket):
    await websocket.send_json({"type": "error", "code": "not_implemented", "message": "send 未实现"})


async def handle_recall(username, msg, websocket):
    await websocket.send_json({"type": "error", "code": "not_implemented", "message": "recall 未实现"})
