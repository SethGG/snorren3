from fastapi import FastAPI, Depends, Cookie, HTTPException, Path
from sse_starlette import EventSourceResponse
from pydantic import BaseModel
from typing import Literal, Dict, List
from sqlalchemy import select, delete
import asyncio
import uuid
import datetime

from . import database as db

####################
# GLOBAL VARIABLES #
####################

app = FastAPI()
games = {}

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


class Game:
    def __init__(self, name: str) -> None:
        self.name = name
        self.connections: dict = {}
        self.inactive_since: datetime.datetime = datetime.datetime.now()
        self.phase = Lobby()

    async def connect(self, id_obj: uuid.UUID) -> asyncio.Queue:
        if id_obj in self.connections and self.connections[id_obj]:
            raise HTTPException(418, "ID already in use")
        queue = asyncio.Queue()
        self.connections[id_obj] = queue
        return queue

    async def disconnect(self, id_obj: uuid.UUID):
        del self.connections[id_obj]

    async def handle_post(self, message: GamePost):
        await self.phase.handle_post(message)


async def game_inactivity_timer(game_obj: Game, seconds: int):
    if game_obj in games.values() and game_obj.inactive_since:
        print("inactivity timer started for %s" % game_obj.name)
        await asyncio.sleep(seconds)
        if game_obj.inactive_since and \
                datetime.datetime.now() - game_obj.inactive_since > datetime.timedelta(seconds=seconds):
            async with db.SessionLocal() as session:
                async with session.begin():
                    query = delete(db.Game).filter(db.Game.name == game_obj.name)
                    await session.execute(query)
                del games[game_obj.name]
        else:
            print("inactivity timer cancelled for %s" % game_obj.name)

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
    asyncio.create_task(game_inactivity_timer(new_game, 30))


@app.get('/games')
async def get_games() -> GameList:
    return GameList(games=list(games.keys()))


@app.post('/games/{game_name}')
async def post_game(post: GamePost, game_obj: Game = Depends(depends_game_obj)):
    await game_obj.handle_post(post)


@app.get('/games/{game_name}')
async def message_stream(game_obj: Game = Depends(depends_game_obj),
                         id_obj: uuid.UUID = Depends(depends_id_obj)) -> GameUpdate:
    queue = await game_obj.connect(id_obj)

    async def event_generator():
        try:
            while True:
                message = await queue.get()
                yield message.dict()
                queue.task_done()
        except asyncio.CancelledError:
            game_obj.disconnect(id_obj)

    response = EventSourceResponse(event_generator(), ping=60)
    response.set_cookie(key="id", value=id_obj.hex)
    return response
