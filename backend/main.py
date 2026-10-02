from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from random import choice, randint
import asyncio
import hashlib
import hmac
import json
import os
from urllib.parse import parse_qsl

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, or_, and_, desc

from .database import init_db, SessionLocal, Player, Car, Number, DealOffer, MarketListing, NpcListing
from .market import market_sync_loop, sync_avito_market, ai_chat, ai_negotiate

load_dotenv()

LETTERS = list("АВЕКМНОРСТУХ")
REGIONS = [26, 23, 77, 78, 50, 52, 61, 116, 123, 196]
DEMO_UID = 900000001
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
ALLOW_DEMO = os.getenv("ALLOW_DEMO_MODE", "0").lower() in {"1", "true", "yes"}

BRANDS = [
    ("BMW", "3 Series", 2019, "2.0 Turbo", "АКПП", 2_150_000),
    ("BMW", "M5", 2021, "4.4 V8", "АКПП", 7_900_000),
    ("Mercedes-Benz", "E-Class", 2020, "2.0 Turbo", "АКПП", 4_300_000),
    ("Toyota", "Camry 70", 2021, "2.5", "АКПП", 2_700_000),
    ("LADA", "Vesta", 2022, "1.6", "МКПП", 990_000),
    ("Audi", "A6", 2019, "2.0 TFSI", "Робот", 3_250_000),
    ("Porsche", "Macan", 2020, "2.0 Turbo", "Робот", 5_100_000),
]
NPC_PHOTOS = {
    "BMW": "https://images.unsplash.com/photo-1555215695-3004980ad54e?auto=format&fit=crop&w=1200&q=85",
    "Mercedes-Benz": "https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?auto=format&fit=crop&w=1200&q=85",
    "Toyota": "https://images.unsplash.com/photo-1621007947382-bb3c3994e3fb?auto=format&fit=crop&w=1200&q=85",
    "LADA": "https://images.unsplash.com/photo-1619767886558-efdc259cde1a?auto=format&fit=crop&w=1200&q=85",
    "Audi": "https://images.unsplash.com/photo-1542282088-fe8426682b8f?auto=format&fit=crop&w=1200&q=85",
    "Porsche": "https://images.unsplash.com/photo-1614200187524-dc4b892acf16?auto=format&fit=crop&w=1200&q=85",
}


def condition_text(v: int) -> str:
    if v >= 90:
        return "Отличное"
    if v >= 75:
        return "Хорошее"
    if v >= 55:
        return "Среднее"
    return "Требует вложений"


def rarity_for(plate: str) -> str:
    digits = "".join(ch for ch in plate if ch.isdigit())
    if digits in {"001", "007", "111", "222", "333", "444", "555", "666", "777", "888", "999"}:
        return "VIP"
    if digits == digits[::-1] or len(set(digits)) == 1:
        return "Очень редкий"
    return "Обычный"


def gen_plate() -> str:
    return f"{choice(LETTERS)} {randint(1, 999):03d} {choice(LETTERS)}{choice(LETTERS)} {choice(REGIONS)}"


def calc_level(rep: int) -> int:
    return max(1, min(50, 1 + rep // 5))


def car_json(c: Car) -> dict:
    return {
        "id": c.id,
        "owner_id": c.owner_id,
        "name": f"{c.brand} {c.model}",
        "brand": c.brand,
        "model": c.model,
        "year": c.year,
        "mileage": c.mileage,
        "engine": c.engine,
        "gearbox": c.gearbox,
        "condition": c.condition,
        "condition_text": condition_text(c.condition),
        "market_price": c.market_price,
        "asking_price": c.asking_price,
        "purchase_price": c.purchase_price,
        "listed": c.listed,
        "list_price": c.list_price,
        "photo": c.photo,
        "number_id": c.number_id,
        "states": {
            "body": c.body,
            "engine": c.engine_state,
            "gearbox": c.gearbox_state,
            "suspension": c.suspension,
            "electronics": c.electronics,
        },
        "damage_note": c.damage_note,
    }


def listing_json(x: MarketListing) -> dict:
    market = max(1, int(x.market_price or x.listed_price))
    delta = round((market - x.listed_price) / market * 100, 1)
    return {
        "id": x.id,
        "title": x.title,
        "name": x.title,
        "brand": x.brand,
        "model": x.model,
        "listed_price": x.listed_price,
        "market_price": x.market_price,
        "year": x.year,
        "mileage": x.mileage,
        "engine": x.engine,
        "gearbox": x.gearbox,
        "drivetrain": x.drivetrain,
        "fuel_type": x.fuel_type,
        "body_type": x.body_type,
        "generation": x.generation,
        "condition": x.condition,
        "condition_text": condition_text(x.condition),
        "seller_name": x.seller_name,
        "seller_type": x.seller_type,
        "location": x.location,
        "photos": x.photos or [],
        "description": x.description,
        "seller_rating": x.seller_rating,
        "deal_delta": delta,
        "status": x.status,
        "last_seen": x.last_seen.isoformat() if x.last_seen else None,
    }


class UserIn(BaseModel):
    telegram_id: int | None = None
    username: str | None = None
    init_data: str | None = None


class PriceIn(BaseModel):
    amount: int = Field(gt=0, le=100_000_000)


class NpcChatIn(BaseModel):
    telegram_id: int | None = None
    listing_id: int
    message: str = Field(min_length=1, max_length=500)
    history: list[dict[str, str]] = Field(default_factory=list)


class MarketChatIn(BaseModel):
    telegram_id: int | None = None
    listing_id: int
    message: str = Field(min_length=1, max_length=500)
    history: list[dict[str, str]] = Field(default_factory=list)
    init_data: str | None = None


class MarketBuyIn(BaseModel):
    telegram_id: int | None = None
    listing_id: int
    amount: int = Field(gt=0, le=100_000_000)
    init_data: str | None = None


class OfferIn(BaseModel):
    seller_id: int
    buyer_id: int | None = None
    car_id: int | None = None
    number_id: int | None = None
    amount: int = Field(gt=0, le=100_000_000)


class AuthHeaderError(Exception):
    pass


def validate_init_data(init_data: str) -> dict:
    """Validate Telegram WebApp initData using the bot token. Returns user data."""
    token = os.getenv("BOT_TOKEN")
    if not token or not init_data:
        raise AuthHeaderError("Telegram initData не предоставлен")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise AuthHeaderError("В initData отсутствует hash")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc_hash, received_hash):
        raise AuthHeaderError("Недействительный initData")
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        auth_date = 0
    if auth_date <= 0 or (int(__import__("time").time()) - auth_date) > int(os.getenv("TELEGRAM_INIT_MAX_AGE_SEC", "86400")):
        raise AuthHeaderError("Срок действия initData истёк")
    user_json = pairs.get("user")
    if not user_json:
        raise AuthHeaderError("В initData отсутствует user")
    return json.loads(user_json)


def resolve_user(request: Request, supplied_id: int | None = None, init_data: str | None = None) -> tuple[int, str | None]:
    raw = init_data or request.headers.get("X-Telegram-Init-Data")
    if raw:
        try:
            user = validate_init_data(raw)
            return int(user["id"]), user.get("username") or user.get("first_name")
        except Exception as exc:
            raise HTTPException(401, str(exc))
    if supplied_id is not None and ALLOW_DEMO:
        return int(supplied_id), None
    raise HTTPException(401, "Откройте AUTO DEALER через Telegram")


async def get_player(db, tg_id: int) -> Player | None:
    return (await db.execute(select(Player).where(Player.telegram_id == tg_id))).scalar_one_or_none()


async def ensure_player(db, tg_id: int, username: str | None = None) -> Player:
    p = await get_player(db, tg_id)
    if not p:
        p = Player(telegram_id=tg_id, username=username, balance=500_000, reputation=0, level=1)
        db.add(p)
        await db.commit()
        await db.refresh(p)
    else:
        changed = False
        if username and p.username != username:
            p.username = username
            changed = True
        p.level = calc_level(p.reputation)
        if changed:
            await db.commit()
    return p


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    stop = asyncio.Event()
    task = asyncio.create_task(market_sync_loop(stop))
    try:
        yield
    finally:
        stop.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="AUTO DEALER", version="2.0.0", lifespan=lifespan)

@app.middleware("http")
async def cache_control(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


@app.get("/", include_in_schema=False)
async def frontend():
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-store, max-age=0"})

@app.get("/favicon.svg", include_in_schema=False)
async def favicon():
    return FileResponse(FRONTEND / "favicon.svg", media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})

@app.get("/health", include_in_schema=False)
@app.get("/api/health")
async def health():
    return {"status": "ok", "game": "AUTO DEALER", "version": "2.0.0"}


@app.post("/api/player")
async def player(data: UserIn, request: Request):
    tg_id, verified_name = resolve_user(request, data.telegram_id, data.init_data)
    username = verified_name or data.username or ("demo_player" if tg_id == DEMO_UID else None)
    async with SessionLocal() as db:
        p = await ensure_player(db, tg_id, username)
        cars_count = (await db.execute(select(Car).where(Car.owner_id == p.id))).scalars().all()
        nums_count = (await db.execute(select(Number).where(Number.owner_id == p.id))).scalars().all()
        return {
            "id": p.id, "telegram_id": p.telegram_id, "username": p.username,
            "balance": p.balance, "reputation": p.reputation, "level": p.level,
            "cars": len(cars_count), "numbers": len(nums_count),
        }


@app.get("/api/cars")
async def cars(request: Request, telegram_id: int | None = None):
    tg_id, _ = resolve_user(request, telegram_id)
    async with SessionLocal() as db:
        p = await get_player(db, tg_id)
        if not p:
            raise HTTPException(404, "Игрок не найден")
        rows = (await db.execute(select(Car).where(Car.owner_id == p.id).order_by(desc(Car.id)))).scalars().all()
        return [car_json(c) for c in rows]


@app.post("/api/search-car")
async def search_car(data: UserIn, request: Request):
    tg_id, verified_name = resolve_user(request, data.telegram_id, data.init_data)
    async with SessionLocal() as db:
        p = await ensure_player(db, tg_id, verified_name or data.username)
        b, m, y, engine_name, gearbox, market = choice(BRANDS)
        condition = randint(58, 96)
        body = max(30, min(100, condition + randint(-12, 5)))
        eng = max(30, min(100, condition + randint(-15, 5)))
        gb = max(35, min(100, condition + randint(-10, 5)))
        suspension = max(35, min(100, condition + randint(-14, 4)))
        electronics = max(40, min(100, condition + randint(-9, 4)))
        mileage = randint(35_000, 220_000)
        ask = round(market * randint(88, 118) / 100 / 1000) * 1000
        seller = choice(["Алексей", "Максим", "Сергей", "Илья", "Денис", "Роман"])
        mood = choice(["Спокойный", "Жадный", "Любит торг", "Срочно нужны деньги", "Перекуп"])
        urgency = "высокая" if mood == "Срочно нужны деньги" else ("низкая" if mood == "Жадный" else "средняя")
        note = "Кузов без очевидных критических проблем."
        if body < 58:
            note = "Есть следы ДТП или серьёзного ремонта кузова."
        if eng < 58:
            note += " Двигателю потребуется внимание."
        item = NpcListing(
            title=f"{b} {m}", brand=b, model=m, year=y, mileage=mileage, engine=engine_name, gearbox=gearbox,
            condition=condition, body=body, engine_state=eng, gearbox_state=gb, suspension=suspension,
            electronics=electronics, market_price=market, asking_price=ask, damage_note=note,
            seller_name=seller, seller_mood=mood, seller_urgency=urgency, photo=NPC_PHOTOS.get(b), status="active",
        )
        db.add(item)
        # Keep the table tiny for a lightweight SQLite deployment.
        old = (await db.execute(select(NpcListing).where(NpcListing.created_at < datetime.utcnow() - timedelta(hours=8)))).scalars().all()
        for x in old:
            x.status = "expired"
        await db.commit(); await db.refresh(item)
        return {"listing": npc_json(item), "seller": {"name": seller, "mood": mood}}


def npc_json(x: NpcListing) -> dict:
    return {
        "id": x.id, "name": x.title, "brand": x.brand, "model": x.model, "year": x.year, "mileage": x.mileage,
        "engine": x.engine, "gearbox": x.gearbox, "condition": x.condition, "condition_text": condition_text(x.condition),
        "market_price": x.market_price, "asking_price": x.asking_price, "seller_name": x.seller_name,
        "seller_mood": x.seller_mood, "seller_urgency": x.seller_urgency, "photo": x.photo, "inspected": x.inspected,
        "states": {"body": x.body, "engine": x.engine_state, "gearbox": x.gearbox_state, "suspension": x.suspension, "electronics": x.electronics},
        "damage_note": x.damage_note,
    }


@app.post("/api/npc/inspect")
async def npc_inspect(request: Request, listing_id: int, telegram_id: int | None = None):
    tg_id, _ = resolve_user(request, telegram_id)
    async with SessionLocal() as db:
        p = await get_player(db, tg_id); item = await db.get(NpcListing, listing_id)
        if not p or not item or item.status != "active": raise HTTPException(404, "Машина уже недоступна")
        cost = 5_000
        if p.balance < cost: raise HTTPException(400, "Недостаточно денег для осмотра")
        p.balance -= cost; item.inspected = True
        await db.commit()
        return {"balance": p.balance, "inspection": {"body": item.body, "engine": item.engine_state, "gearbox": item.gearbox_state, "suspension": item.suspension, "electronics": item.electronics, "note": item.damage_note}}


@app.post("/api/npc/chat")
async def npc_chat(data: NpcChatIn, request: Request):
    tg_id, _ = resolve_user(request, data.telegram_id)
    async with SessionLocal() as db:
        item = await db.get(NpcListing, data.listing_id)
        if not item or item.status != "active": raise HTTPException(404, "Объявление недоступно")
        result = await ai_chat(tg_id, item, data.message, data.history)
        return {"ok": True, **result}


@app.post("/api/npc/buy")
async def npc_buy(data: MarketBuyIn, request: Request):
    tg_id, _ = resolve_user(request, data.telegram_id, data.init_data)
    async with SessionLocal() as db:
        p = await get_player(db, tg_id); item = await db.get(NpcListing, data.listing_id)
        if not p or not item or item.status != "active": raise HTTPException(404, "Машина уже недоступна")
        result = await ai_negotiate(tg_id, item, data.amount)
        if not result["accepted"]: return {"ok": False, **result}
        price = int(result["agreed_price"])
        if p.balance < price: raise HTTPException(400, "Недостаточно денег")
        p.balance -= price; p.reputation += 1; p.level = calc_level(p.reputation)
        car = Car(owner_id=p.id, brand=item.brand, model=item.model, year=item.year, mileage=item.mileage,
                  engine=item.engine, gearbox=item.gearbox, condition=item.condition, body=item.body,
                  engine_state=item.engine_state, gearbox_state=item.gearbox_state, suspension=item.suspension,
                  electronics=item.electronics, market_price=item.market_price, asking_price=price,
                  purchase_price=price, damage_note=item.damage_note, photo=item.photo)
        db.add(car); item.status = "sold"
        await db.commit(); await db.refresh(car)
        return {"ok": True, "balance": p.balance, "car": car_json(car), **result}


@app.post("/api/repair")
async def repair(request: Request, car_id: int, telegram_id: int | None = None):
    tg_id, _ = resolve_user(request, telegram_id)
    async with SessionLocal() as db:
        p = await get_player(db, tg_id); c = await db.get(Car, car_id)
        if not p or not c or c.owner_id != p.id: raise HTTPException(404, "Машина не найдена")
        cost = max(10_000, int((100 - c.condition) * 3_300))
        if p.balance < cost: raise HTTPException(400, "Недостаточно денег")
        c.condition = min(100, c.condition + max(8, (100 - c.condition) // 2)); c.body = min(100, c.body + 10)
        c.engine_state = min(100, c.engine_state + 8); c.gearbox_state = min(100, c.gearbox_state + 6)
        c.suspension = min(100, c.suspension + 9); c.electronics = min(100, c.electronics + 5)
        p.balance -= cost
        await db.commit()
        return {"balance": p.balance, "cost": cost, "car": car_json(c)}


@app.get("/api/market")
@app.get("/api/market/avito")
async def market_catalog(
    request: Request,
    telegram_id: int | None = None,
    min_price: int = 0,
    max_price: int | None = None,
    brand: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    gearbox: str | None = None,
    body_type: str | None = None,
    sort: str = "bargain",
    limit: int = 100,
):
    tg_id, _ = resolve_user(request, telegram_id)
    async with SessionLocal() as db:
        player = await get_player(db, tg_id)
        if not player:
            raise HTTPException(404, "Игрок не найден")
        active_rows = (await db.execute(select(MarketListing).where(MarketListing.status == "active"))).scalars().all()
        if len([x for x in active_rows if x.listed_price <= 500_000]) < 24:
            await seed_demo_market()
            active_rows = (await db.execute(select(MarketListing).where(MarketListing.status == "active"))).scalars().all()
        if os.getenv("APIFY_TOKEN"):
            fresh = [x for x in active_rows if x.source not in {"system", "demo"}]
            if not fresh:
                try:
                    await asyncio.wait_for(sync_avito_market(), timeout=60)
                except Exception:
                    log.exception("One-shot market refresh failed")
        query = select(MarketListing).where(MarketListing.status == "active")
        # По умолчанию показываем только то, что игрок реально может купить.
        effective_max = player.balance if max_price is None else max(0, max_price)
        if min_price > 0:
            query = query.where(MarketListing.listed_price >= min_price)
        if effective_max > 0:
            query = query.where(MarketListing.listed_price <= effective_max)
        if brand and brand.lower() != "все":
            query = query.where(MarketListing.brand.ilike(f"%{brand.strip()}%"))
        if year_from:
            query = query.where(MarketListing.year >= year_from)
        if year_to:
            query = query.where(MarketListing.year <= year_to)
        if gearbox and gearbox.lower() != "все":
            query = query.where(MarketListing.gearbox.ilike(f"%{gearbox.strip()}%"))
        if body_type and body_type.lower() != "все":
            query = query.where(MarketListing.body_type.ilike(f"%{body_type.strip()}%"))
        if sort == "price_asc":
            query = query.order_by(MarketListing.listed_price.asc())
        elif sort == "year_desc":
            query = query.order_by(MarketListing.year.desc(), MarketListing.listed_price.asc())
        elif sort == "mileage_asc":
            query = query.order_by(MarketListing.mileage.asc())
        else:
            # Лучшие варианты по разнице между рынком и ценой объявления.
            query = query.order_by(desc(MarketListing.market_price - MarketListing.listed_price), MarketListing.last_seen.desc())
        rows = (await db.execute(query.limit(max(1, min(limit, 100))))).scalars().all()
        return [listing_json(x) for x in rows]


@app.get("/api/market/filters")
async def market_filters(request: Request, telegram_id: int | None = None):
    tg_id, _ = resolve_user(request, telegram_id)
    async with SessionLocal() as db:
        if not await get_player(db, tg_id):
            raise HTTPException(404, "Игрок не найден")
        rows = (await db.execute(select(MarketListing).where(MarketListing.status == "active"))).scalars().all()
        brands = sorted({x.brand for x in rows if x.brand and x.brand != "Unknown"})
        gearboxes = sorted({x.gearbox for x in rows if x.gearbox and x.gearbox != "Не указано"})
        bodies = sorted({x.body_type for x in rows if x.body_type})
        return {"brands": brands, "gearboxes": gearboxes, "body_types": bodies, "min_year": min((x.year for x in rows if x.year), default=2000), "max_year": max((x.year for x in rows if x.year), default=2026)}


@app.get("/api/market/status")
async def market_status():
    async with SessionLocal() as db:
        rows = (await db.execute(select(MarketListing).where(MarketListing.status == "active"))).scalars().all()
        external = [x for x in rows if x.source not in {"system", "demo"}]
        last = max((x.last_seen for x in external if x.last_seen), default=None)
        return {"active": len(rows), "external_active": len(external), "last_sync": last.isoformat() if last else None, "cities": os.getenv("AVITO_CITIES", os.getenv("AVITO_CITY_SLUG", "kislovodsk")).split(","), "source_ready": bool(os.getenv("APIFY_TOKEN"))}


@app.post("/api/market/refresh")
async def market_refresh(request: Request):
    admin = request.headers.get("X-Admin-Key")
    expected = os.getenv("ADMIN_KEY")
    if not expected or not hmac.compare_digest(admin or "", expected):
        raise HTTPException(403, "Недостаточно прав")
    try:
        return {"ok": True, "count": await sync_avito_market()}
    except Exception as exc:
        raise HTTPException(502, str(exc))


@app.post("/api/market/chat")
async def market_chat(data: MarketChatIn, request: Request):
    tg_id, _ = resolve_user(request, data.telegram_id, data.init_data)
    async with SessionLocal() as db:
        if not await get_player(db, tg_id): raise HTTPException(404, "Игрок не найден")
        item = await db.get(MarketListing, data.listing_id)
        if not item or item.status != "active": raise HTTPException(404, "Объявление недоступно")
        result = await ai_chat(tg_id, item, data.message, data.history)
        return {"ok": True, **result}


@app.post("/api/market/buy")
async def market_buy(data: MarketBuyIn, request: Request):
    tg_id, _ = resolve_user(request, data.telegram_id, data.init_data)
    async with SessionLocal() as db:
        p = await get_player(db, tg_id); item = await db.get(MarketListing, data.listing_id)
        if not p or not item or item.status != "active": raise HTTPException(404, "Объявление недоступно")
        result = await ai_negotiate(tg_id, item, data.amount)
        if not result["accepted"]: return {"ok": False, **result}
        price = int(result["agreed_price"])
        if p.balance < price: raise HTTPException(400, "Недостаточно денег")
        p.balance -= price; p.reputation += 1; p.level = calc_level(p.reputation)
        car = Car(owner_id=p.id, brand=item.brand, model=item.model, year=item.year or 2020, mileage=item.mileage,
                  engine=item.engine or "Не указано", gearbox=item.gearbox or "Не указано", condition=item.condition,
                  body=item.condition, engine_state=item.condition, gearbox_state=item.condition,
                  suspension=item.condition, electronics=item.condition, market_price=item.market_price,
                  asking_price=price, purchase_price=price, damage_note=f"Продавец: {item.seller_name}",
                  photo=(item.photos or [None])[0])
        db.add(car); item.status = "sold"
        await db.commit(); await db.refresh(car)
        return {"ok": True, "balance": p.balance, "car": car_json(car), **result}


@app.get("/api/numbers")
async def numbers(request: Request, telegram_id: int | None = None, market: bool = False):
    tg_id, _ = resolve_user(request, telegram_id)
    async with SessionLocal() as db:
        p = await get_player(db, tg_id)
        if not p: raise HTTPException(404, "Игрок не найден")
        query = select(Number)
        if market:
            query = query.where(Number.listed == True, Number.owner_id != p.id)
        else:
            query = query.where(Number.owner_id == p.id)
        rows = (await db.execute(query.order_by(desc(Number.id)).limit(100))).scalars().all()
        return [{"id": n.id, "plate": n.plate, "rarity": n.rarity, "price": n.price, "list_price": n.list_price, "listed": n.listed, "owner_id": n.owner_id, "car_id": n.car_id} for n in rows]


@app.post("/api/number")
async def get_number(data: UserIn, request: Request):
    tg_id, _ = resolve_user(request, data.telegram_id, data.init_data)
    async with SessionLocal() as db:
        p = await get_player(db, tg_id)
        if not p: raise HTTPException(404, "Игрок не найден")
        cost = 20_000
        if p.balance < cost: raise HTTPException(400, "Нужно 20 000 ₽")
        plate = None
        for _ in range(200):
            candidate = gen_plate()
            exists = (await db.execute(select(Number.id).where(Number.plate == candidate))).scalar_one_or_none()
            if not exists:
                plate = candidate
                break
        if not plate: raise HTTPException(503, "Не удалось подобрать свободный номер")
        rarity = rarity_for(plate)
        value = {"Обычный": 15_000, "Очень редкий": 250_000, "VIP": 850_000}[rarity]
        n = Number(plate=plate, rarity=rarity, owner_id=p.id, price=value)
        p.balance -= cost
        db.add(n)
        await db.commit(); await db.refresh(n)
        return {"balance": p.balance, "number": {"id": n.id, "plate": n.plate, "rarity": n.rarity, "price": n.price}}


@app.post("/api/plate/install")
async def plate_install(request: Request, number_id: int, car_id: int, telegram_id: int | None = None):
    tg_id, _ = resolve_user(request, telegram_id)
    async with SessionLocal() as db:
        p = await get_player(db, tg_id); n = await db.get(Number, number_id); c = await db.get(Car, car_id)
        if not p or not n or not c or n.owner_id != p.id or c.owner_id != p.id: raise HTTPException(404, "Номер или машина не найдены")
        if n.listed: raise HTTPException(400, "Сначала снимите номер с рынка")
        if n.car_id: raise HTTPException(400, "Этот номер уже установлен")
        old = (await db.execute(select(Number).where(Number.car_id == c.id))).scalar_one_or_none()
        if old: raise HTTPException(400, "На машине уже установлен номер")
        n.car_id = c.id; c.number_id = n.id
        await db.commit()
        return {"ok": True}


@app.post("/api/plate/remove")
async def plate_remove(request: Request, car_id: int, telegram_id: int | None = None):
    tg_id, _ = resolve_user(request, telegram_id)
    async with SessionLocal() as db:
        p = await get_player(db, tg_id); c = await db.get(Car, car_id)
        if not p or not c or c.owner_id != p.id: raise HTTPException(404, "Машина не найдена")
        if not c.number_id: raise HTTPException(400, "На машине нет номера")
        n = await db.get(Number, c.number_id)
        if n: n.car_id = None
        c.number_id = None
        await db.commit()
        return {"ok": True}


@app.post("/api/list-car")
async def list_car(request: Request, car_id: int, data: PriceIn, telegram_id: int | None = None):
    tg_id, _ = resolve_user(request, telegram_id)
    async with SessionLocal() as db:
        p = await get_player(db, tg_id); c = await db.get(Car, car_id)
        if not p or not c or c.owner_id != p.id: raise HTTPException(404, "Машина не найдена")
        if c.listed: raise HTTPException(400, "Машина уже выставлена")
        if c.number_id: raise HTTPException(400, "Перед продажей снимите номер")
        c.listed = True; c.list_price = data.amount
        await db.commit()
        return {"ok": True}


@app.post("/api/unlist-car")
async def unlist_car(request: Request, car_id: int, telegram_id: int | None = None):
    tg_id, _ = resolve_user(request, telegram_id)
    async with SessionLocal() as db:
        p = await get_player(db, tg_id); c = await db.get(Car, car_id)
        if not p or not c or c.owner_id != p.id: raise HTTPException(404, "Машина не найдена")
        c.listed = False; c.list_price = None
        await db.commit()
        return {"ok": True}


@app.get("/api/market/cars")
async def market_player_cars(request: Request, telegram_id: int | None = None):
    tg_id, _ = resolve_user(request, telegram_id)
    async with SessionLocal() as db:
        p = await get_player(db, tg_id)
        if not p: raise HTTPException(404, "Игрок не найден")
        rows = (await db.execute(select(Car).where(Car.listed == True, Car.owner_id != p.id).order_by(desc(Car.id)).limit(100))).scalars().all()
        return [car_json(c) | {"seller_id": c.owner_id, "seller_price": c.list_price} for c in rows]


@app.post("/api/list-number")
async def list_number(request: Request, number_id: int, data: PriceIn, telegram_id: int | None = None):
    tg_id, _ = resolve_user(request, telegram_id)
    async with SessionLocal() as db:
        p = await get_player(db, tg_id); n = await db.get(Number, number_id)
        if not p or not n or n.owner_id != p.id: raise HTTPException(404, "Номер не найден")
        if n.car_id: raise HTTPException(400, "Снимите номер с машины перед продажей")
        n.listed = True; n.list_price = data.amount
        await db.commit()
        return {"ok": True}


@app.post("/api/unlist-number")
async def unlist_number(request: Request, number_id: int, telegram_id: int | None = None):
    tg_id, _ = resolve_user(request, telegram_id)
    async with SessionLocal() as db:
        p = await get_player(db, tg_id); n = await db.get(Number, number_id)
        if not p or not n or n.owner_id != p.id: raise HTTPException(404, "Номер не найден")
        n.listed = False; n.list_price = None
        await db.commit(); return {"ok": True}


@app.post("/api/offer")
async def create_offer(data: OfferIn, request: Request):
    tg_id, _ = resolve_user(request, data.buyer_id)
    async with SessionLocal() as db:
        buyer = await get_player(db, tg_id); seller = await db.get(Player, data.seller_id)
        if not buyer or not seller or buyer.id == seller.id: raise HTTPException(400, "Недопустимые участники сделки")
        if bool(data.car_id) == bool(data.number_id): raise HTTPException(400, "Нужно выбрать автомобиль или номер")
        if data.amount > buyer.balance: raise HTTPException(400, "Недостаточно денег")
        if data.car_id:
            c = await db.get(Car, data.car_id)
            if not c or c.owner_id != seller.id or not c.listed: raise HTTPException(400, "Автомобиль недоступен")
        if data.number_id:
            n = await db.get(Number, data.number_id)
            if not n or n.owner_id != seller.id or not n.listed or n.car_id: raise HTTPException(400, "Номер недоступен")
        pending = (await db.execute(select(DealOffer).where(DealOffer.buyer_id == buyer.id, DealOffer.seller_id == seller.id, DealOffer.status == "pending"))).scalars().all()
        if len(pending) >= 5: raise HTTPException(429, "Слишком много активных предложений")
        o = DealOffer(seller_id=seller.id, buyer_id=buyer.id, car_id=data.car_id, number_id=data.number_id, amount=data.amount)
        db.add(o); await db.commit(); await db.refresh(o)
        return {"id": o.id, "status": o.status}


@app.get("/api/offers")
async def get_offers(request: Request, telegram_id: int | None = None):
    tg_id, _ = resolve_user(request, telegram_id)
    async with SessionLocal() as db:
        p = await get_player(db, tg_id)
        if not p: raise HTTPException(404, "Игрок не найден")
        rows = (await db.execute(select(DealOffer).where(or_(DealOffer.buyer_id == p.id, DealOffer.seller_id == p.id), DealOffer.status == "pending").order_by(desc(DealOffer.created_at)).limit(100))).scalars().all()
        result = []
        for o in rows:
            result.append({"id": o.id, "seller_id": o.seller_id, "buyer_id": o.buyer_id, "car_id": o.car_id, "number_id": o.number_id, "amount": o.amount, "incoming": o.seller_id == p.id, "created_at": o.created_at.isoformat() if o.created_at else None})
        return result


@app.post("/api/offer/{offer_id}/accept")
async def accept_offer(offer_id: int, request: Request, telegram_id: int | None = None):
    tg_id, _ = resolve_user(request, telegram_id)
    async with SessionLocal() as db:
        seller = await get_player(db, tg_id); o = await db.get(DealOffer, offer_id)
        if not seller or not o or o.seller_id != seller.id or o.status != "pending": raise HTTPException(400, "Предложение недоступно")
        buyer = await db.get(Player, o.buyer_id)
        if not buyer or buyer.balance < o.amount: raise HTTPException(400, "У покупателя недостаточно денег")
        if o.car_id:
            c = await db.get(Car, o.car_id)
            if not c or c.owner_id != seller.id or not c.listed: raise HTTPException(409, "Автомобиль уже недоступен")
            buyer.balance -= o.amount; seller.balance += o.amount; c.owner_id = buyer.id; c.listed = False; c.list_price = None
        else:
            n = await db.get(Number, o.number_id)
            if not n or n.owner_id != seller.id or not n.listed or n.car_id: raise HTTPException(409, "Номер уже недоступен")
            buyer.balance -= o.amount; seller.balance += o.amount; n.owner_id = buyer.id; n.listed = False; n.list_price = None
        o.status = "accepted"
        await db.commit(); return {"ok": True}


@app.post("/api/offer/{offer_id}/reject")
async def reject_offer(offer_id: int, request: Request, telegram_id: int | None = None):
    tg_id, _ = resolve_user(request, telegram_id)
    async with SessionLocal() as db:
        p = await get_player(db, tg_id); o = await db.get(DealOffer, offer_id)
        if not p or not o or (o.seller_id != p.id and o.buyer_id != p.id) or o.status != "pending": raise HTTPException(400, "Предложение недоступно")
        o.status = "rejected"; await db.commit(); return {"ok": True}


@app.post("/api/offers/cancel/{offer_id}")
async def cancel_offer(offer_id: int, request: Request, telegram_id: int | None = None):
    return await reject_offer(offer_id, request, telegram_id)
