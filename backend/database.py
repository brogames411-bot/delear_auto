import os
from datetime import datetime
from urllib.parse import urlsplit
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import BigInteger, Integer, String, Boolean, ForeignKey, Text, JSON, DateTime, UniqueConstraint, Index, text as sql_text

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./auto_dealer.db")

class Base(DeclarativeBase):
    pass

class Player(Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    balance: Mapped[int] = mapped_column(Integer, default=500_000)
    reputation: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Car(Base):
    __tablename__ = "cars"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    brand: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(60))
    year: Mapped[int] = mapped_column(Integer)
    mileage: Mapped[int] = mapped_column(Integer)
    engine: Mapped[str] = mapped_column(String(40))
    gearbox: Mapped[str] = mapped_column(String(30))
    condition: Mapped[int] = mapped_column(Integer)
    body: Mapped[int] = mapped_column(Integer)
    engine_state: Mapped[int] = mapped_column(Integer)
    gearbox_state: Mapped[int] = mapped_column(Integer)
    suspension: Mapped[int] = mapped_column(Integer)
    electronics: Mapped[int] = mapped_column(Integer)
    market_price: Mapped[int] = mapped_column(Integer)
    asking_price: Mapped[int] = mapped_column(Integer)
    damage_note: Mapped[str] = mapped_column(Text, default="")
    number_id: Mapped[int | None] = mapped_column(ForeignKey("numbers.id"), nullable=True)
    listed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    list_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    photo: Mapped[str | None] = mapped_column(String(700), nullable=True)
    purchase_price: Mapped[int | None] = mapped_column(Integer, nullable=True)

class Number(Base):
    __tablename__ = "numbers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plate: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    rarity: Mapped[str] = mapped_column(String(20))
    owner_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    price: Mapped[int] = mapped_column(Integer)
    listed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    list_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    car_id: Mapped[int | None] = mapped_column(ForeignKey("cars.id"), nullable=True)

class DealOffer(Base):
    __tablename__ = "deal_offers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    car_id: Mapped[int | None] = mapped_column(ForeignKey("cars.id"), nullable=True)
    number_id: Mapped[int | None] = mapped_column(ForeignKey("numbers.id"), nullable=True)
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class MarketListing(Base):
    __tablename__ = "market_listings"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_market_source_item"),
        Index("ix_market_active_seen", "status", "last_seen"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(20), default="avito", index=True)
    source_id: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(160))
    brand: Mapped[str] = mapped_column(String(40), default="Unknown")
    model: Mapped[str] = mapped_column(String(60), default="Unknown")
    listed_price: Mapped[int] = mapped_column(Integer)
    market_price: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer, default=0)
    mileage: Mapped[int] = mapped_column(Integer, default=0)
    engine: Mapped[str] = mapped_column(String(40), default="Не указано")
    gearbox: Mapped[str] = mapped_column(String(30), default="Не указано")
    drivetrain: Mapped[str] = mapped_column(String(30), default="")
    fuel_type: Mapped[str] = mapped_column(String(30), default="")
    body_type: Mapped[str] = mapped_column(String(50), default="")
    generation: Mapped[str] = mapped_column(String(80), default="")
    condition: Mapped[int] = mapped_column(Integer, default=75)
    seller_name: Mapped[str] = mapped_column(String(120), default="Авито-продавец")
    seller_type: Mapped[str] = mapped_column(String(20), default="private")
    location: Mapped[str] = mapped_column(String(200), default="")
    url: Mapped[str] = mapped_column(String(500), default="")
    photos: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    seller_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)

class NpcListing(Base):
    __tablename__ = "npc_listings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    brand: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(60))
    year: Mapped[int] = mapped_column(Integer)
    mileage: Mapped[int] = mapped_column(Integer)
    engine: Mapped[str] = mapped_column(String(40))
    gearbox: Mapped[str] = mapped_column(String(30))
    condition: Mapped[int] = mapped_column(Integer)
    body: Mapped[int] = mapped_column(Integer)
    engine_state: Mapped[int] = mapped_column(Integer)
    gearbox_state: Mapped[int] = mapped_column(Integer)
    suspension: Mapped[int] = mapped_column(Integer)
    electronics: Mapped[int] = mapped_column(Integer)
    market_price: Mapped[int] = mapped_column(Integer)
    asking_price: Mapped[int] = mapped_column(Integer)
    damage_note: Mapped[str] = mapped_column(Text, default="")
    seller_name: Mapped[str] = mapped_column(String(80), default="Частник")
    seller_mood: Mapped[str] = mapped_column(String(40), default="Спокойный")
    seller_urgency: Mapped[str] = mapped_column(String(40), default="обычная")
    photo: Mapped[str | None] = mapped_column(String(700), nullable=True)
    inspected: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def _migrate_sqlite() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return
    async with engine.begin() as conn:
        async def columns(table: str) -> set[str]:
            rows = (await conn.execute(sql_text(f"PRAGMA table_info({table})"))).all()
            return {str(r[1]) for r in rows}
        migrations = {
            "players": {"created_at": "DATETIME"},
            "cars": {"photo": "VARCHAR(700)", "purchase_price": "INTEGER"},
            "deal_offers": {"created_at": "DATETIME"},
            "market_listings": {
                "description": "TEXT DEFAULT ''",
                "seller_rating": "INTEGER",
            },
        }
        for table, additions in migrations.items():
            existing = await columns(table)
            for col, definition in additions.items():
                if col not in existing:
                    await conn.execute(sql_text(f"ALTER TABLE {table} ADD COLUMN {col} {definition}"))

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate_sqlite()
