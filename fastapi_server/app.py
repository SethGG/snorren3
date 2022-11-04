from fastapi import Cookie, FastAPI, APIRouter, WebSocket, HTTPException, WebSocketDisconnect, \
    Depends, Path
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyCookie
from fastapi.responses import JSONResponse
from typing import List
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select
from dataclasses import dataclass, field
from starlette.exceptions import WebSocketException
from json.decoder import JSONDecodeError
import uuid
import asyncio
import datetime
import time

from . import models, schemas
from .database import SessionLocal, engine

app = FastAPI()

games = {}


@dataclass
class Game:
    connections: dict = field(default_factory=dict)
    inactive_since: datetime.datetime = field(default_factory=datetime.datetime.now)

    async def on_connect(self, ws: WebSocket, id: uuid.UUID):
        if id in self.connections and self.connections[id]:
            raise WebSocketException(code=1008, reason="ID already in use")
        await ws.accept()
        await ws.send_json({"event": "id", "data": id.hex})
        self.connections[id] = ws

  #  async def on_join(self, id: uuid)

    async def on_disconnect(self, id: uuid.UUID, db: AsyncSession):
        query = select(models.GameConnection, models.Game.in_progress, models.Player.name) \
            .join(models.GameConnection.game).outerjoin(models.GameConnection.player) \
            .filter(models.GameConnection.conn_id == id.hex)
        result = await db.execute(query)
        db_connection = result.one_or_none()
        print(db_connection)
        if db_connection:
            if not db_connection.in_progress or not db_connection.name:
                db.delete(db_connection.GameConnection)
                await db.commit()
                del self.connections[id]
            else:
                self.connections[id] = None
        else:
            del self.connections[id]

# @dataclass
# class Connection:
#     websocket: WebSocket
#     has_joined: bool = False
#     is_player: bool = False


###################
# HTTP API Routes #
###################

# Exeption Handlers #


@app.exception_handler(IntegrityError)
def db_exception_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"detail": {"msg": str(exc.orig), "type": type(exc).__name__}})

# Authentication #


websocket_id = APIKeyCookie(name="id", description="WebSocket Connection ID")

# Dependancies #


# def get_db():
#     db = SessionLocal()
#     print("!!! new session !!!")
#     try:
#         yield db
#     finally:
#         db.close()


# def get_game(game_name: str = Path(..., title="Game Name"), db: Session = Depends(get_db)):
#     db_game = db.query(models.Game).get(game_name)
#     if not db_game:
#         raise HTTPException(status_code=404, detail="Game not found")
#     return db_game


# def get_connection(game: models.Game = Depends(get_game), id: str = Depends(websocket_id)):
#     try:
#         id_obj = uuid.UUID(id, version=4)
#     except ValueError:
#         raise HTTPException(status_code=403, detail="Not authenticated")
#     if id_obj in games[game.name].connections:
#         return id_obj
#     else:
#         raise HTTPException(status_code=403, detail="Not authenticated")


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    async with SessionLocal() as db:
        async with db.begin():
            query = select(models.Game)
            result = await db.execute(query)
            for game in result.scalars().all():
                games[game.name] = Game()
        #         await asyncio.create_task(game_inactivity_timer(game.name, 10))

# Root Routes #


root_router = APIRouter(prefix="/api", tags=["Root Page"])


# @root_router.get("/games", response_model=List[schemas.Game])
# def get_games(db: Session = Depends(get_db)):
#     db_games = db.query(models.Game.name, models.Game.in_progress,
#                         func.count(models.Player.game_name).label("number_of_players")
#                         ).outerjoin(models.Player).group_by(models.Game.name).all()
#     return db_games


@root_router.post("/games", response_model=schemas.GameCreate)
async def create_game(game: schemas.GameCreate):
    async with SessionLocal() as db:
        async with db.begin():
            db_game = models.Game(name=game.name)
            db.add(db_game)
            await db.commit()
            games[game.name] = Game()
            return db_game


# @root_router.get("/test")
# def test():
#     print("yeet1")
#     time.sleep(10)
#     print("yeet2")
#     return


# Game Routes #

# game_router = APIRouter(prefix="/api/games", tags=["Game Page"])


# @game_router.post("/{game_name}", response_model=schemas.Player, response_model_exclude_unset=True)
# def join_game(player: schemas.PlayerCreate, game: models.Game = Depends(get_game),
#               conn_id: uuid.UUID = Depends(get_connection), db: Session = Depends(get_db)):
#     # add game connection to database
#     db_conn = models.GameConnection(conn_id=conn_id.hex, game_name=game.name)
#     db.add(db_conn)
#     response = db_conn
#     # add player to database is game is not in progress and name is provided
#     if not game.in_progress and player.name:
#         db_player = models.Player(conn_id=conn_id.hex, game_name=game.name, name=player.name)
#         db.add(db_player)
#         response = db_player
#     db.commit()
#     return response


# @game_router.get("/{game_name}/players")
# def get_player_data(game: Game = Depends(get_game)):
#     coroutine = list(game.guests.values())[0].ws.send_json(
#         {"event": "id", "data": "yeet"})
#     asyncio.run(coroutine)
#     return "yeet"


# @game_router.get("/{game_name}/phase")
# async def get_phase_data(player: Player = Depends(get_player)):
#     return player.phase_info


# @game_router.post("/{game_name}/phase")
# async def post_phase_data():
#     pass

app.include_router(root_router)
# app.include_router(game_router)

########################
# WebSocket API Routes #
########################


async def game_inactivity_timer(game_name, seconds):
    if game_name in games and games[game_name].inactive_since:
        print("inactivity timer started for %s" % game_name)
        await asyncio.sleep(seconds)
        if games[game_name].inactive_since and datetime.datetime.now() - \
                games[game_name].inactive_since > datetime.timedelta(seconds=seconds):
            with SessionLocal() as db:
                db.query(models.Game).filter(models.Game.name == game_name).delete()
                db.commit()
                del games[game_name]
            print("%s removed" % game_name)
        else:
            print("inactivity timer cancelled for %s" % game_name)


async def ws_extract_game(websocket: WebSocket, game_name: str = Path(...)):
    """
    Takes the websocket object and game name provided in the path and returns the in-memory game
    object if the game exists.
    """
    if game_name not in games:
        raise WebSocketException(code=1008, reason="Game not found")
    return games[game_name]


async def ws_extract_id(websocket: WebSocket, id: str = Cookie(None),
                        game: Game = Depends(ws_extract_game)):
    """
    Takes the websocket object, the connection id cookie and the in-memory game object and returns
    the UUID object if the id is not already in use.
    """
    try:
        id_obj = uuid.UUID(id, version=4)
    except (TypeError, ValueError):
        id_obj = uuid.uuid4()
    return id_obj


@app.websocket("/{game_name}")
async def game_websocket(websocket: WebSocket, id: uuid.UUID = Depends(ws_extract_id),
                         game: Game = Depends(ws_extract_game), game_name: str = Path(...)):
    await game.on_connect(websocket, id)
    try:
        while True:
            try:
                data = await websocket.receive_json()
                print(data)
            except JSONDecodeError:
                await websocket.send_json({"event": "error", "data": "Invalid JSON Payload"})
    except WebSocketDisconnect:
        print("ws disconnect")
        async with SessionLocal() as db:
            async with db.begin():
                await game.on_disconnect(id, db)
            # db_connection = \
            #     db.query(models.GameConnection, models.Game.in_progress, models.Player.name) \
            #     .join(models.GameConnection.game).outerjoin(models.GameConnection.player) \
            #     .filter(models.GameConnection.conn_id == id.hex).one_or_none()
            # if db_connection:
            #     if not db_connection.in_progress or not db_connection.name:
            #         db.delete(db_connection.GameConnection)
            #         db.commit()
            #         del game.connections[id]
            #     else:
            #         game.connections[id] = None
            # else:
            #     del game.connections[id]
            # if not game.connections.values():
            #     game.inactive_since = datetime.datetime.now()
            #     await asyncio.create_task(game_inactivity_timer(game_name, 10))


##########################
# Serve Static React App #
##########################


class SPAStaticFiles(StaticFiles):
    async def lookup_path(self, path: str):
        full_path, stat_result = await super().lookup_path(path)
        if stat_result is None:
            return await super().lookup_path("index.html")
        return (full_path, stat_result)


app.mount("/", StaticFiles(directory="./react-app/build", html=True), name="SPA")
