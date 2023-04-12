from fastapi import FastAPI, Depends, Cookie, HTTPException, Path, Request
from fastapi.staticfiles import StaticFiles
from sse_starlette import EventSourceResponse
from pydantic import BaseModel, create_model
from typing import Literal, Dict, List, Optional, ClassVar
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


class GameUpdateBase(BaseModel):
    retry: int = 5


class GameUpdateMessage(GameUpdateBase):
    event: Literal["message"]
    data: str


class GameUpdatePhase(GameUpdateBase):
    event: Literal["phase_update"]
    data: Dict


class GameUpdatePlayers(GameUpdateBase):
    event: Literal["player_update"]
    data: Dict


GameUpdate = GameUpdateMessage | GameUpdatePhase | GameUpdatePlayers


class GameCreate(BaseModel):
    name: str


class GamePostJoin(BaseModel):
    class GamePostJoinPlayer(BaseModel):
        type: Literal["player"]
        name: str

    class GamePostJoinSpectator(BaseModel):
        type: Literal["spectator"]

    DataModels: ClassVar = GamePostJoinPlayer | GamePostJoinSpectator

    event: Literal["join"]
    data: DataModels


class GamePostVote(BaseModel):
    class GamePostVoteName(BaseModel):
        name: str

    DataModels: ClassVar = GamePostVoteName

    event: Literal["vote"]
    data: DataModels


roles = {"snor": (int, ...), "nazi": (int, ...)}


class GamePostStart(BaseModel):
    class GamePostStartData(BaseModel):
        RoleSelection: ClassVar = create_model("RoleSelection", **roles)

        role_selection: RoleSelection
        options: Optional[Dict]

    DataModels: ClassVar = GamePostStartData

    event: Literal["start"]
    data: GamePostStartData


GamePost = GamePostJoin | GamePostVote | GamePostStart


class GameList(BaseModel):
    games: List[str]


#################
# PHASE CLASSES #
#################


class Phase:
    def __init__(self, game: "Game") -> None:
        self.game = game

    async def handle_post(self, conn: "Connection", message: GamePost):
        try:
            handler = getattr(self, f"on_{message.event}")
            await handler(conn, message.data)
        except AttributeError:
            raise HTTPException(418, "Invalid event name")

    async def on_join(self, conn: "Connection", data: GamePostJoin.DataModels):
        conn.is_spectator = True


class Lobby(Phase):
    async def on_join(self, conn: "Connection", data: GamePostJoin.DataModels):
        pass

##############
# GAME CLASS #
##############


class Connection:
    def __init__(self, id_obj: uuid.UUID) -> None:
        self.id_obj = id_obj
        self.queue = asyncio.Queue()
        self.active = True
        self.is_player = False
        self.is_spectator = False

    async def listen_for_updates(self) -> GameUpdateMessage:
        return await self.queue.get()

    async def send_message(self, message: str) -> None:
        await self.queue.put(GameUpdateMessage(event="message", data=message))


class Game:
    def __init__(self, name: str) -> None:
        self.name = name
        self.connections = {}
        self.in_progress = False
        self.inactive_since = datetime.datetime.now()
        self.phase = Lobby(game=self)

    async def connect(self, id_obj: uuid.UUID) -> Connection:
        if id_obj in self.connections:
            # Scenario 1: Game has not started and ID is already in use
            if not self.in_progress:
                raise HTTPException(418, "ID already in use")
            connection = self.connections[id_obj]
            # Scenario 2: Game has started and the player with this ID is already connected
            if connection.active:
                raise HTTPException(418, "ID is already connected")
            connection.active = True
            logger.debug(f"Game {self.name} - Reconnection of existing connection, ID: {id_obj.hex}")
        else:
            # Scenario 3: This is a new ID
            connection = Connection(id_obj=id_obj)
            self.connections[id_obj] = connection
            logger.debug(f"Game {self.name} - New connection added, ID: {id_obj.hex}")
        # Mark game as active if it was inactive
        if self.inactive_since:
            self.inactive_since = None
            logger.debug(f"Game {self.name} - Marked as active")
        # Send the connection a confirmation message
        await connection.send_message("connected!")
        return connection

    async def disconnect(self, id_obj: uuid.UUID):
        if id_obj in self.connections:
            connection = self.connections[id_obj]
            connection.active = False
            logger.debug(f"Game {self.name} - Connection marked as inactive, ID: {id_obj.hex}")
            if not self.in_progress:
                del self.connections[id_obj]
                logger.debug(f"Game {self.name} - Connection removed, ID: {id_obj.hex}")
            if not any(c.active for c in self.connections.values()):
                self.inactive_since = datetime.datetime.now()

    async def handle_post(self, id_obj: uuid.UUID, message: GamePost):
        if id_obj not in self.connections:
            raise HTTPException(418, "You are not connected to this game")
        await self.phase.handle_post(self.connections[id_obj], message)


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
        logger.debug(f"Connection ID - Valid ID provided, ID: {id_obj.hex}")
    except (TypeError, ValueError):
        id_obj = uuid.uuid4()
        logger.debug(f"Connection ID - Invalid or no ID provided, newly generated ID: {id_obj.hex}")
    return id_obj


async def depends_game_obj(game_name: str = Path(...)) -> Game:
    if game_name not in games:
        raise HTTPException(404, "Game not found")
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
async def game_message_stream(request: Request,
                              game_obj: Game = Depends(depends_game_obj),
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
    response.set_cookie(key="id", value=id_obj.hex, path=request.url.path)
    return response

app.mount("/test", StaticFiles(directory="fastapi_server/test_html", html=True), name="test_html")
