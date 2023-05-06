from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, attribute_keyed_dict
from sqlalchemy import ForeignKeyConstraint, ForeignKey, UniqueConstraint
from typing import Optional
import uuid


class Base(DeclarativeBase):
    pass


class Game(Base):
    __tablename__ = "games"

    name: Mapped[str] = mapped_column(primary_key=True)
    in_progress: Mapped[bool] = mapped_column(default=False)
    phase: Mapped[str] = mapped_column(default="lobby")

    players: Mapped[dict[str, "Player"]] = relationship(lazy="selectin", collection_class=attribute_keyed_dict("name"))
    phases: Mapped[list["Phase"]] = relationship(order_by="asc(Phase.number)", lazy="selectin")


class Player(Base):
    __tablename__ = "players"

    conn_id: Mapped[uuid.UUID]
    game_name: Mapped[str] = mapped_column(ForeignKey("games.name"), primary_key=True)
    name: Mapped[str] = mapped_column(primary_key=True)
    alive: Mapped[bool] = mapped_column(default=True)
    lover: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (
        UniqueConstraint("conn_id", "game_name"),
    )

    role: Mapped["PlayerHasRole"] = relationship(lazy="selectin")


class PlayerHasRole(Base):
    __tablename__ = "player_has_role"

    game_name: Mapped[str] = mapped_column(primary_key=True)
    player_name: Mapped[str] = mapped_column(primary_key=True)
    type: Mapped[str]

    __table_args__ = (
        ForeignKeyConstraint(["game_name", "player_name"], ["players.game_name", "players.name"]),
    )

    __mapper_args__ = {
        "polymorphic_on": "type",
    }


class Scooterjeugd(PlayerHasRole):
    __tablename__ = "player_has_role_scooterjeugd"

    game_name: Mapped[str] = mapped_column(primary_key=True)
    player_name: Mapped[str] = mapped_column(primary_key=True)
    ability_used: Mapped[bool] = mapped_column(default=False)
    team: str = "burgers"

    __table_args__ = (
        ForeignKeyConstraint(["game_name", "player_name"], [
                             "player_has_role.game_name", "player_has_role.player_name"]),
    )

    __mapper_args__ = {
        "polymorphic_identity": "scooterjeugd"
    }


class Burger(PlayerHasRole):
    team: str = "burgers"

    __mapper_args__ = {
        "polymorphic_identity": "burger"
    }


class Phase(Base):
    __tablename__ = "phases"

    number: Mapped[int] = mapped_column(primary_key=True)
    game_name: Mapped[str] = mapped_column(ForeignKey("games.name"))
    night_number: Mapped[int]
    type: Mapped[str]

    __mapper_args__ = {
        "polymorphic_on": "type"
    }


class PhaseScooterjeugd(Phase):
    __tablename__ = "phases_scooterjeugd"

    phase_number: Mapped[int] = mapped_column(ForeignKey("phases.number"), primary_key=True)
    player_game_name: Mapped[str]
    player_name: Mapped[str]
    disturbed: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (
        ForeignKeyConstraint(["player_game_name", "player_name"],
                             ["player_has_role_scooterjeugd.game_name", "player_has_role_scooterjeugd.player_name"]),
    )

    __mapper_args__ = {
        "polymorphic_identity": "scooterjeugd"
    }

    player: Mapped[Scooterjeugd] = relationship()
