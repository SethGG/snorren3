from pydantic import BaseModel


class GameCreate(BaseModel):
    name: str

    class Config:
        orm_mode = True


class Game(GameCreate):
    in_progress: bool
    number_of_players: int


class PlayerCreate(BaseModel):
    name: str = None


class Player(PlayerCreate):
    conn_id: str
    game_name: str

    class Config:
        orm_mode = True
