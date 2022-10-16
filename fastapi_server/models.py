from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, ForeignKeyConstraint
from sqlalchemy.orm import relationship

from .database import Base


class Game(Base):
    __tablename__ = "games"

    name = Column(String, primary_key=True, index=True)
    in_progress = Column(Boolean, default=False)
    phase = Column(String, default="lobby")
    day_number = Column(Integer, default=1)

    connections = relationship("GameConnection", back_populates="game", cascade="all, delete",)
    players = relationship("Player", back_populates="game", cascade="all, delete",)


class GameConnection(Base):
    __tablename__ = "game_connections"

    conn_id = Column(String, primary_key=True, index=True)
    game_name = Column(String, ForeignKey("games.name"))

    game = relationship("Game", back_populates="connections")
    player = relationship("Player", back_populates="connection", cascade="all, delete",)


class Player(Base):
    __tablename__ = "players"

    conn_id = Column(String, ForeignKey("game_connections.conn_id"), unique=True)
    game_name = Column(String, ForeignKey("games.name"), primary_key=True)
    name = Column(String, primary_key=True)
    is_alive = Column(Boolean, default=True)
    is_lover = Column(Boolean, default=False)

    connection = relationship("GameConnection", back_populates="player")
    game = relationship("Game", back_populates="players")
    info = relationship("PlayerInformation", back_populates="player", cascade="all, delete",)


class PlayerInformation(Base):
    __tablename__ = "player_information"

    game_name = Column(String, primary_key=True)
    player_name = Column(String, primary_key=True)
    other_player_name = Column(String, primary_key=True)
    is_role = Column(Boolean, primary_key=True)
    info = Column(String, primary_key=True)

    __table_args__ = (ForeignKeyConstraint([game_name, player_name],
                                           [Player.game_name, Player.name]),)

    player = relationship("Player",
                          foreign_keys="[PlayerInformation.game_name, \
                                        PlayerInformation.player_name]",
                          back_populates="info")
