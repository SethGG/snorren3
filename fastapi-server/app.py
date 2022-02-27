from fastapi import FastAPI, APIRouter, WebSocket, HTTPException, WebSocketDisconnect, Query, status, Depends, Path
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyQuery
from starlette.types import Receive, Scope, Send
from starlette.responses import Response
from starlette.applications import Starlette
from starlette.routing import Mount
from typing import Type
import uuid
import os


app = FastAPI()

class Guest:
    def __init__(self, id_obj: uuid.UUID, ws: WebSocket, game: 'Game'):
        self.id_obj = id_obj
        self.ws = ws
        self.game = game
        self.spectator = False

    player_info = "You don't know shit about players"
    phase_info = "You don't know shit about the phase"

class Player:
    def __init__(self, name: str, id_obj: uuid.UUID, ws: WebSocket, game: 'Game'):
        self.name = Name
        self.id_obj = id_obj
        self.ws = ws
        self.game = game

    @classmethod
    def fromGuest(cls: Type['Player'], guest: Guest, name: str):
        return cls(name, guest.id_obj, guest.ws, guest.game)

    player_info = "Player Yeet"
    phase_info = "Phase Yeet"

class Game:
    def __init__(self):
        self.players = {}
        self.guests = {}

games = {"kaas": Game()}

###################
# HTTP API Routes #
###################

websocket_id = APIKeyQuery(name="id", description="WebSocket Connection ID")

async def get_game(game_name: str = Path(..., title="Game Name")):
    if game_name not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    return games[game_name]

async def get_player(game = Depends(get_game), id: str = Depends(websocket_id)):
    try:
        id_obj = uuid.UUID(id, version=4)
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid ID")
    for player in game.players.values():
        if player.id_obj == id_obj:
            return player
    else:
        raise HTTPException(status_code=403, detail="No user found with provided ID")


home_router = APIRouter(prefix="/games", tags=["Home Page"])

@home_router.get("/")
async def get_games():
    return "yeet"

@home_router.post("/")
async def create_game():
    pass

game_router = APIRouter(prefix="/games/{game_name}", tags=["Game Page"])

@game_router.post("/")
async def join_game():
    pass

@game_router.get("/players")
async def get_player_data(player: Player = Depends(get_player)):
    return player.player_info

@game_router.get("/phase")
async def get_phase_data(player: Player = Depends(get_player)):
    return player.phase_info

@game_router.post("/phase")
async def post_phase_data():
    pass

app.include_router(home_router)
app.include_router(game_router)

########################
# WebSocket API Routes #
########################

async def ws_extract_id(websocket: WebSocket, id: str = Query(None)):
    id_obj = None
    try:
        id_obj = uuid.UUID(id, version=4)
    except TypeError:
        id_obj = uuid.uuid4()
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    return id_obj

async def ws_extract_game(websocket: WebSocket, game_name: str = Path(...)):
    if game_name not in games:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    return games[game_name]

@app.websocket("/{game_name}")
async def game_websocket(websocket: WebSocket, id_obj: uuid.UUID = Depends(ws_extract_id), game: Game = Depends(ws_extract_game)):
    if id_obj and game:
        await websocket.accept()
        await websocket.send_json({"event": "id", "data": id_obj.hex})
        game.guests[id_obj] = Guest(id_obj, websocket, game)
        try:
            await websocket.receive_json()
        except WebSocketDisconnect:
            print("ws disconnect")
            pass

##########################
# Serve Static React App #
##########################

class SPAStaticFiles(StaticFiles):
    async def lookup_path(self, path: str):
        full_path, stat_result = await super().lookup_path(path)
        if stat_result is None:
            return await super().lookup_path("index.html")
        return (full_path, stat_result)

routes = [
    Mount('/api', app=app, name="api"),
    Mount('/', StaticFiles(directory="../react-app/build", html=True), name="SPA")
]

star = Starlette(routes=routes)
