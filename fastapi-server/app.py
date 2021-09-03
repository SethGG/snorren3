from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from typing import Optional
import uuid
import os


app = FastAPI()

class SingePageApplication(StaticFiles):
    def __init__(self, directory: os.PathLike, index="index.html"):
        self.index = index
        super().__init__(directory=directory, packages=None, html=True, check_dir=True)

    async def lookup_path(self, path: str):
        full_path, stat_result = await super().lookup_path(path)
        if stat_result is None:
            return await super().lookup_path(self.index)

        return (full_path, stat_result)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, id: Optional[str] = Query(None)):
    await websocket.accept()
    id = str(uuid.uuid4())
    await websocket.send_json({"event": "id", "data": id})
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        pass

app.mount(path="/", app=SingePageApplication(directory="../react-app/build"), name="SPA")
