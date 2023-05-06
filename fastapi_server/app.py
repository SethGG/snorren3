from fastapi import FastAPI, Depends, Cookie, HTTPException, Path, Request
from fastapi.encoders import jsonable_encoder
from fastapi.staticfiles import StaticFiles
from sse_starlette import EventSourceResponse
from pydantic import BaseModel, create_model, Field, validator, PrivateAttr
from typing import Literal, Dict, List, Optional, ClassVar
from uvicorn.logging import ColourizedFormatter
from dataclasses import dataclass, field
import asyncio
import uuid
import datetime
import logging
import aiofiles
import aiofiles.os
import json
import glob


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
    class GameUpdatePlayersPlayer(BaseModel):
        name: str
        role: str = "unknown"
        lover: bool = False
        mayor: bool = False

    DataModel: ClassVar = GameUpdatePlayersPlayer

    event: Literal["player_update"]
    data: list[GameUpdatePlayersPlayer]


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
        _RoleSelection = create_model("RoleSelection", **roles)

        role_selection: _RoleSelection
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


class BasePhase(BaseModel):
    type: Optional[str] = None

    @validator("type", pre=True, always=True)
    def check_type(cls, v):
        print(f"cls: {cls}, v: {v}")
        if v is None:
            return cls._type
        elif v != cls._type:
            raise ValueError("wrong phase type")
        return v

    async def handle_post(self, conn: "Connection", message: GamePost):
        try:
            handler = getattr(self, f"on_{message.event}")
            await handler(conn, message.data)
        except AttributeError:
            raise HTTPException(418, "Invalid event name")


class GameStart(BasePhase):
    _type = "game_start"

    kaas: str


class Lobby(BasePhase):
    _type = "lobby"

    async def on_start(self, data: GamePostStart.DataModels) -> None:
        pass


Phase = GameStart | Lobby


##############
# GAME CLASS #
##############

@dataclass
class Connection:
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)

    async def listen_for_updates(self) -> GameUpdateMessage:
        return await self.queue.get()

    async def send_message(self, message: str) -> None:
        await self.queue.put(GameUpdateMessage(event="message", data=message))

    async def send_player_update(self, data: list[GameUpdatePlayers.DataModel]) -> None:
        await self.queue.put(GameUpdatePlayers(event="player_update", data=data))


class Player(BaseModel):
    name: str
    alive: bool = True
    lover: bool = False
    role: Optional[str] = None


class Game(BaseModel):
    name: str
    players: dict[uuid.UUID, Player] = {}
    in_progress: bool = False
    phase: Phase = Field(default_factory=Lobby)

    _connections: dict[uuid.UUID, Connection] = PrivateAttr(default={})
    _inactive_since: Optional[datetime.datetime] = PrivateAttr(default_factory=datetime.datetime.now)
    _spectators: set[uuid.UUID] = PrivateAttr(default=set())

    @property
    def connections(self):
        return self._connections

    @property
    def inactive_since(self):
        return self._inactive_since

    @property
    def spectators(self):
        return self._spectators

    def mark_active(self):
        self._inactive_since = None

    def mark_inactive(self):
        self._inactive_since = datetime.datetime.now()

    def get_player_info(self, id_obj) -> list[GameUpdatePlayers.DataModel]:
        if id_obj in self.connections:
            return [GameUpdatePlayers.DataModel(name=player.name) for player in self.players.values()]

    async def send_message_to_all(self, message: str) -> None:
        for connection in self.connections.values():
            await connection.send_message(message)

    async def send_player_update_to_all(self) -> None:
        for id_obj, connection in self.connections.items():
            await connection.send_player_update(self.get_player_info(id_obj))

    async def connect(self, id_obj: uuid.UUID) -> Connection:
        if id_obj in self.connections:
            raise HTTPException(418, "ID already in use")
        connection = Connection()
        self.connections[id_obj] = connection
        logger.debug(f"Game {self.name} - New connection added, ID: {id_obj.hex}")
        if self.inactive_since:
            self.mark_active()
            logger.debug(f"Game {self.name} - Marked as active")
        await connection.send_message(f"Welcome to {self.name}!")
        if id_obj in self.players:
            await self.send_player_update_to_all()
        else:
            await connection.send_player_update(self.get_player_info(id_obj))
        return connection

    async def disconnect(self, id_obj: uuid.UUID):
        if id_obj in self.connections:
            del self.connections[id_obj]
            logger.debug(f"Game {self.name} - Connection removed, ID: {id_obj.hex}")
            if id_obj in self.spectators:
                self.spectators.remove(id_obj)
            elif id_obj in self.players:
                if not self.in_progress:
                    del self.players[id_obj]
            if not self.connections:
                self.mark_inactive()

    async def join(self, id_obj: uuid.UUID, data: GamePostJoin.DataModels):
        if id_obj in self.connections and not (id_obj in self.players or id_obj in self.spectators):
            if data.type == "spectator":
                self.spectators.add(id_obj)
                print(self.spectators)
            elif data.type == "player" and not self.in_progress:
                self.players[id_obj] = Player(name=data.name)

    async def handle_post(self, id_obj: uuid.UUID, message: GamePost):
        if id_obj not in self.connections:
            raise HTTPException(418, "You are not connected to this game")
        if message.event == "join":
            await self.join(id_obj, message.data)
        else:
            await self.phase.handle_post(self.connections[id_obj], message)

    async def save_json(self):
        file_name = f"game:{self.name}.json"
        async with aiofiles.open(file_name, mode="w") as f:
            game_obj_jsonable = jsonable_encoder(self)
            await f.write(json.dumps(game_obj_jsonable, indent=4))
        logger.debug(f"Game {self.name} - game state has been saved to {file_name}")

    async def delete_json(self):
        file_name = f"game:{self.name}.json"
        if await aiofiles.os.path.exists(file_name):
            await aiofiles.os.remove(file_name)
        logger.debug(f"Game {self.name} - game state file {file_name} has been deleted")


async def game_inactivity_timer(game_obj: Game, seconds: int):
    if game_obj in games.values() and game_obj.inactive_since:
        logger.debug(
            f"Inactivity timer - Game {game_obj.name} will be deleted after {seconds} seconds of inactivity")
        await asyncio.sleep(seconds)
        if game_obj.inactive_since and \
                datetime.datetime.now() - game_obj.inactive_since > datetime.timedelta(seconds=seconds):
            del games[game_obj.name]
            logger.debug(f"Inactivity timer - Game {game_obj.name} has been deleted")
            await game_obj.delete_json()
        else:
            logger.debug(f"Inactivity timer - Game {game_obj.name} was active in the past {seconds} seconds "
                         "and will not be deleted")

###############
# API STARTUP #
###############


@app.on_event("startup")
async def startup():
    game_files = glob.glob("game:*.json")
    for file in game_files:
        restored_game = Game.parse_file(file)
        games[restored_game.name] = restored_game
        logger.debug(f"Startup - Game {restored_game.name} has been restored from {file}")
        asyncio.create_task(game_inactivity_timer(restored_game, 60))


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

    new_game = Game(name=game.name)
    games[game.name] = new_game
    logger.debug(f"Create game - New game {game.name} created")
    await new_game.save_json()
    asyncio.create_task(game_inactivity_timer(new_game, 30))


@app.get('/games')
async def get_games() -> GameList:
    return GameList(games=list(games.keys()))


@app.post('/games/{game_name}')
async def post_game(post: GamePost, game_obj: Game = Depends(depends_game_obj),
                    id_obj: uuid.UUID = Depends(depends_id_obj)):
    await game_obj.handle_post(id_obj, post)


@app.get('/games/{game_name}/json')
async def game_json(game_obj: Game = Depends(depends_game_obj)):
    return game_obj


@app.get('/games/{game_name}')
async def connect_game(request: Request,
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
