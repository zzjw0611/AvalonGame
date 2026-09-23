"""Transactional JSON room snapshots; SQLite locally, PostgreSQL in deployment."""
from __future__ import annotations

import copy
import hashlib
import secrets
import time
import uuid
from typing import Callable, TypeVar

from sqlalchemy import JSON, Float, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool

T = TypeVar('T')


class Base(DeclarativeBase):
    pass


class Guest(Base):
    __tablename__ = 'guests'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(32))
    expires_at: Mapped[float] = mapped_column(Float)


class Room(Base):
    __tablename__ = 'rooms'
    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    host_id: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[float] = mapped_column(Float)
    state: Mapped[dict] = mapped_column(JSON)


class Database:
    def __init__(self, url: str):
        kwargs = {'pool_pre_ping': True}
        if url.startswith('sqlite'):
            kwargs['connect_args'] = {'check_same_thread': False}
            if ':memory:' in url:
                kwargs['poolclass'] = StaticPool
        self.engine = create_engine(url, **kwargs)

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    def create_guest(self, name: str) -> dict:
        token = secrets.token_urlsafe(36)
        guest = Guest(id=uuid.uuid4().hex, token_hash=hashlib.sha256(token.encode()).hexdigest(),
                      name=name, expires_at=time.time() + 30 * 86400)
        with Session(self.engine, expire_on_commit=False) as db, db.begin():
            db.add(guest)
        return {'id': guest.id, 'name': guest.name, 'token': token, 'expires_at': guest.expires_at}

    def authenticate(self, token: str) -> dict | None:
        if not 20 <= len(token) <= 256:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        with Session(self.engine) as db:
            guest = db.scalar(select(Guest).where(Guest.token_hash == digest, Guest.expires_at > time.time()))
            return {'id': guest.id, 'name': guest.name} if guest else None

    def revoke(self, guest_id: str) -> None:
        with Session(self.engine) as db, db.begin():
            guest = db.get(Guest, guest_id)
            if guest:
                guest.expires_at = 0

    def insert_room(self, state: dict) -> None:
        with Session(self.engine) as db, db.begin():
            db.add(Room(code=state['code'], host_id=state['host_id'], status=state['status'],
                        state=state, revision=0, updated_at=time.time()))

    def read(self, code: str) -> dict | None:
        with Session(self.engine) as db:
            row = db.get(Room, code)
            return copy.deepcopy(row.state) if row else None

    def transact(self, code: str, fn: Callable[[dict], T]) -> T:
        # PostgreSQL row lock + application room lock; no network calls in fn.
        with Session(self.engine) as db, db.begin():
            row = db.scalar(select(Room).where(Room.code == code).with_for_update())
            if row is None:
                raise LookupError('房间不存在')
            state = copy.deepcopy(row.state)
            result = fn(state)
            row.state, row.status = state, state['status']
            row.revision += 1
            row.updated_at = time.time()
            return result

    def list_states(self, status: str | None = None, limit: int = 200) -> list[dict]:
        with Session(self.engine) as db:
            query = select(Room).order_by(Room.updated_at.desc()).limit(limit)
            if status:
                query = query.where(Room.status == status)
            return [copy.deepcopy(row.state) for row in db.scalars(query)]
