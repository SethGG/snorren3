from fastapi import FastAPI, Depends, Cookie, HTTPException, Path
from sse_starlette import EventSourceResponse
from pydantic import BaseModel
from typing import Literal, Dict, List
from sqlalchemy import select, delete
from uvicorn.logging import ColourizedFormatter
import asyncio
import uuid
import datetime
import logging

from . import database as db

####################
# GLOBAL VARIABLES #
####################

app = FastAPI()
games = {}

logger = logging.getLogger(__name__)
logger.setLevel('DEBUG')
handler = logging.StreamHandler()
handler.setFormatter(ColourizedFormatter("%(levelprefix)s %(message)s"))
logger.addHandler(handler)

###################
# PYDANTIC MODELS #
###################


class GameUpdate(BaseModel):
    event: Literal["player_update", "phase_update"]
    data: Dict
    retry: int = 5


class GamePost(BaseModel):
    event: str
    data: Dict


class GameCreate(BaseModel):
    name: str


class GameList(BaseModel):
    games: List[str]

#################
# PHASE CLASSES #
#################


class Phase:
    async def handle_post(self, message: GamePost):
        try:
            handler = getattr(self, f"on_{message.event}")
            await handler(message.data)
        except AttributeError:
            raise HTTPException(418, "Invalid event name")


class Lobby(Phase):
    async def on_join(self, data: Dict):
        print("I want to join!")

##############
# GAME CLASS #
##############


class Connection:
    def __init__(self, id_obj: uuid.UUID) -> None:
        self.id_obj = id_obj
        self.queue = asyncio.Queue()
        self.active = True

    async def listen_for_updates(self) -> GameUpdate:
        return await self.queue.get()


class Game:
    def __init__(self, name: str) -> None:
        self.name = name
        self.connections = {}
        self.in_progress = False
        self.inactive_since = datetime.datetime.now()
        self.phase = Lobby()

    async def connect(self, id_obj: uuid.UUID) -> Connection:
        if id_obj in self.connections:
            if not self.in_progress:
                raise HTTPException(418, "ID already in use")
            connection = self.connections[id_obj]
            if connection.connected:
                raise HTTPException(418, "ID is already connected")
            connection.connected = True
            logger.debug(f"Game {self.name} - Reconnection of existing connection, ID: {id_obj.hex}")
        else:
            connection = Connection(id_obj=id_obj)
            self.connections[id_obj] = connection
            logger.debug(f"Game {self.name} - New connection added, ID: {id_obj.hex}")
        if self.inactive_since:
            self.inactive_since = None
            logger.debug(f"Game {self.name} - Marked as active")
        return connection

    async def disconnect(self, id_obj: uuid.UUID):
        if id_obj in self.connections:
            connection = self.connections[id_obj]
            connection.active = False
            logger.debug(f"Game {self.name} - Connection marked as inactive, ID: {id_obj.hex}")
            if not self.in_progress:
                del self.connections[id_obj]
                logger.debug(f"Game {self.name} - Connection removed, ID: {id_obj.hex}")
            if not any(c.connected for c in self.connections):
                self.inactive_since = datetime.datetime.now()

    async def handle_post(self, id_obj: uuid.UUID, message: GamePost):
        if id_obj not in self.connections:
            raise HTTPException(418, "You are not connected to this game")
        await self.phase.handle_post(message)


async def game_inactivity_timer(game_obj: Game, seconds: int):
    if game_obj in games.values() and game_obj.inactive_since:
        logger.debug(
            f"Inactivity timer - Game {game_obj.name} will be deleted after {seconds} seconds without activity")
        await asyncio.sleep(seconds)
        if game_obj.inactive_since and \
                datetime.datetime.now() - game_obj.inactive_since > datetime.timedelta(seconds=seconds):
            async with db.SessionLocal() as session:
                async with session.begin():
                    query = delete(db.Game).filter(db.Game.name == game_obj.name)
                    await session.execute(query)
            del games[game_obj.name]
            logger.debug(f"Inactivity timer - Game {game_obj.name} has been deleted")
        else:
            logger.debug(f"Inactivity timer - Game {game_obj.name} was active in the past {seconds} seconds "
                         "and will not be deleted")

###############
# API STARTUP #
###############


@app.on_event("startup")
async def startup():
    async with db.engine.begin() as conn:
        await conn.run_sync(db.Base.metadata.create_all)
    async with db.SessionLocal() as session:
        query = select(db.Game)
        result = await session.execute(query)
        for game in result.scalars().all():
            new_game = Game(name=game.name)
            games[game.name] = new_game
            asyncio.create_task(game_inactivity_timer(new_game, 60))


####################
# API DEPENDENCIES #
####################


async def depends_id_obj(id: str = Cookie(None)) -> uuid.UUID:
    try:
        id_obj = uuid.UUID(id, version=4)
    except (TypeError, ValueError):
        id_obj = uuid.uuid4()
        logger.debug(f"Connection ID - Invalid or no ID provided, newly generated ID: {id_obj.hex}")
    return id_obj


async def depends_game_obj(game_name: str = Path(...)) -> Game:
    if game_name not in games:
        raise HTTPException(418, "Game not found")
    return games[game_name]

#################
# API ENDPOINTS #
#################


@app.post('/games')
async def create_game(game: GameCreate):
    if game.name in games:
        raise HTTPException(418, f"A game with the name {game.name} already exists")

    async with db.SessionLocal() as session:
        async with session.begin():
            db_game = db.Game(name=game.name)
            session.add(db_game)

    new_game = Game(name=game.name)
    games[game.name] = new_game
    logger.debug(f"Create game - New game {game.name} created")
    asyncio.create_task(game_inactivity_timer(new_game, 30))


@app.get('/games')
async def get_games() -> GameList:
    return GameList(games=list(games.keys()))


@app.post('/games/{game_name}')
async def post_game(post: GamePost, game_obj: Game = Depends(depends_game_obj),
                    id_obj: uuid.UUID = Depends(depends_id_obj)):
    await game_obj.handle_post(id_obj, post)


@app.get('/games/{game_name}')
async def message_stream(game_obj: Game = Depends(depends_game_obj),
                         id_obj: uuid.UUID = Depends(depends_id_obj)) -> GameUpdate:
    connection = await game_obj.connect(id_obj)

    async def event_generator():
        try:
            while True:
                message = await connection.listen_for_updates()
                yield message.dict()
        except asyncio.CancelledError:
            await game_obj.disconnect(id_obj)
            asyncio.create_task(game_inactivity_timer(game_obj, 30))

    response = EventSourceResponse(event_generator(), ping=60)
    response.set_cookie(key="id", value=id_obj.hex)
    return response
