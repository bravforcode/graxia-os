"""
Paper Trading Engine — Graxia Signal → Simulated Execution → DB logging

Flow:
  1. Poll signal_service (POST /api/signal) every 60s
  2. If signal has direction != "FLAT" and no open position → simulate fill
  3. Track open position with SL/TP
  4. Log everything to PostgreSQL (graxia-db)

Risk:
  - 0.25% account per trade
  - Max 1 position at a time
  - Session filter: 08:00-17:00 UTC
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import yfinance as yf
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# --- Config ---
SIGNAL_SERVICE_URL = os.getenv("SIGNAL_SERVICE_URL", "http://graxia-signal:8752")
DB_URL = os.environ.get("DATABASE_URL", "")
if not DB_URL:
    raise RuntimeError("DATABASE_URL environment variable is required")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.001"))  # 0.10% — matches backtest RiskPolicy
INITIAL_BALANCE = float(os.getenv("INITIAL_BALANCE", "100000"))
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "1"))
SPREAD_PTS = float(os.getenv("SPREAD_PTS", "3.0"))
SLIPPAGE_PTS = float(os.getenv("SLIPPAGE_PTS", "1.0"))
SYMBOL = os.getenv("SYMBOL", "XAUUSD")
AUTO_POLL = os.getenv("AUTO_POLL", "true").lower() == "true"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("paper_executor")

engine = create_engine(DB_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# --- DB Models ---
class PaperTrade(Base):
    __tablename__ = "paper_trades"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False)
    direction = Column(String(16), nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    sl_distance = Column(Float, nullable=True)
    tp_distance = Column(Float, nullable=True)
    lot_size = Column(Float, nullable=False)
    pnl = Column(Float, nullable=True)
    commission = Column(Float, default=0)
    spread_cost = Column(Float, default=0)
    status = Column(String(16), default="open")
    opened_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    closed_at = Column(DateTime(timezone=True), nullable=True)
    signal_confidence = Column(Float, nullable=True)
    signal_json = Column(Text, nullable=True)


class PaperPosition(Base):
    __tablename__ = "paper_positions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(Integer, nullable=False)
    symbol = Column(String(32), nullable=False)
    direction = Column(String(16), nullable=False)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)
    sl_price = Column(Float, nullable=True)
    tp_price = Column(Float, nullable=True)
    lot_size = Column(Float, nullable=False)
    floating_pnl = Column(Float, default=0)
    opened_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PaperPortfolio(Base):
    __tablename__ = "paper_portfolio"
    id = Column(Integer, primary_key=True, autoincrement=True)
    balance = Column(Float, nullable=False)
    equity = Column(Float, nullable=False)
    total_pnl = Column(Float, default=0)
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


# --- Pydantic Models ---
class TradeResponse(BaseModel):
    trade_id: int
    symbol: str
    direction: str
    entry_price: float
    sl_price: float
    tp_price: float
    lot_size: float
    status: str
    opened_at: str


class PortfolioResponse(BaseModel):
    balance: float
    equity: float
    total_pnl: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    open_positions: int


class SignalPayload(BaseModel):
    symbol: str
    direction: str
    confidence: float
    sl_distance: float
    current_price: float
    timestamp: str
    features_used: int


# --- App ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    _init_portfolio()
    logger.info("Paper Executor started — DB ready, portfolio initialized")
    if AUTO_POLL:
        asyncio.create_task(_poll_loop())
    yield
    logger.info("Paper Executor shutting down")


app = FastAPI(title="Graxia Paper Executor", lifespan=lifespan)

API_KEY = os.environ.get("PAPER_EXECUTOR_API_KEY", "")


def _check_auth(request: Request) -> None:
    if API_KEY:
        key = request.headers.get("X-API-Key", "")
        if key != API_KEY:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Unauthorized")


def _init_portfolio():
    with SessionLocal() as db:
        existing = db.query(PaperPortfolio).first()
        if not existing:
            p = PaperPortfolio(
                balance=INITIAL_BALANCE,
                equity=INITIAL_BALANCE,
                total_pnl=0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
            )
            db.add(p)
            db.commit()
            logger.info(f"Portfolio initialized: ${INITIAL_BALANCE:,.2f}")


# --- Core Logic ---
def _get_portfolio(db) -> PaperPortfolio:
    p = db.query(PaperPortfolio).first()
    if not p:
        _init_portfolio()
        p = db.query(PaperPortfolio).first()
    return p


def _get_open_position(db) -> PaperPosition | None:
    return db.query(PaperPosition).first()


def _calculate_lot_size(balance: float, sl_distance: float) -> float:
    risk_amount = balance * RISK_PER_TRADE
    if sl_distance <= 0:
        return 0.01
    lot_size = risk_amount / (sl_distance * 100)
    # P1 fix: round DOWN to 0.01 (INV-007), not banker's round
    import math

    return max(0.01, math.floor(lot_size * 100) / 100.0)


def _open_trade(signal: SignalPayload) -> TradeResponse | None:
    with SessionLocal() as db:
        portfolio = _get_portfolio(db)
        existing_pos = _get_open_position(db)

        if existing_pos:
            logger.info("Already have open position — skipping")
            return None

        direction = signal.direction
        if direction not in ("BUY", "SELL"):
            logger.info(f"Signal direction={direction} — no trade")
            return None

        price = signal.current_price
        sl_distance = signal.sl_distance

        if direction == "BUY":
            entry_price = price + SPREAD_PTS / 2 + SLIPPAGE_PTS
            sl_price = entry_price - sl_distance
            tp_price = entry_price + sl_distance * 2
        else:
            entry_price = price - SPREAD_PTS / 2 - SLIPPAGE_PTS
            sl_price = entry_price + sl_distance
            tp_price = entry_price - sl_distance * 2

        lot_size = _calculate_lot_size(portfolio.balance, sl_distance)
        spread_cost = SPREAD_PTS * lot_size * 100

        trade = PaperTrade(
            symbol=signal.symbol,
            direction=direction,
            entry_price=round(entry_price, 2),
            sl_distance=sl_distance,
            tp_distance=round(sl_distance * 2, 2),
            lot_size=lot_size,
            commission=0,
            spread_cost=round(spread_cost, 2),
            status="open",
            signal_confidence=signal.confidence,
            signal_json=json.dumps(signal.model_dump()),
        )
        db.add(trade)
        db.commit()
        db.refresh(trade)

        position = PaperPosition(
            trade_id=trade.id,
            symbol=signal.symbol,
            direction=direction,
            entry_price=round(entry_price, 2),
            current_price=price,
            sl_price=round(sl_price, 2),
            tp_price=round(tp_price, 2),
            lot_size=lot_size,
            floating_pnl=0,
        )
        db.add(position)
        db.commit()

        portfolio.total_trades += 1
        portfolio.balance -= spread_cost
        db.commit()

        logger.info(
            f"OPENED {direction} {lot_size} lots @ {entry_price:.2f} "
            f"SL={sl_price:.2f} TP={tp_price:.2f} spread=${spread_cost:.2f}"
        )

        return TradeResponse(
            trade_id=trade.id,
            symbol=signal.symbol,
            direction=direction,
            entry_price=round(entry_price, 2),
            sl_price=round(sl_price, 2),
            tp_price=round(tp_price, 2),
            lot_size=lot_size,
            status="open",
            opened_at=trade.opened_at.isoformat(),
        )


def _check_sl_tp(current_price: float):
    with SessionLocal() as db:
        pos = _get_open_position(db)
        if not pos:
            return

        should_close = False
        close_price = current_price

        if pos.direction == "BUY":
            if current_price <= pos.sl_price:
                should_close = True
                close_price = pos.sl_price
                logger.info(f"SL HIT @ {current_price:.2f}")
            elif current_price >= pos.tp_price:
                should_close = True
                close_price = pos.tp_price
                logger.info(f"TP HIT @ {current_price:.2f}")
        else:
            if current_price >= pos.sl_price:
                should_close = True
                close_price = pos.sl_price
                logger.info(f"SL HIT @ {current_price:.2f}")
            elif current_price <= pos.tp_price:
                should_close = True
                close_price = pos.tp_price
                logger.info(f"TP HIT @ {current_price:.2f}")

        if should_close:
            _close_position(pos, close_price, db)
        else:
            if pos.direction == "BUY":
                pos.floating_pnl = (current_price - pos.entry_price) * pos.lot_size * 100
            else:
                pos.floating_pnl = (pos.entry_price - current_price) * pos.lot_size * 100
            pos.current_price = current_price
            db.commit()


def _close_position(pos: PaperPosition, close_price: float, db):
    trade = db.query(PaperTrade).filter(PaperTrade.id == pos.trade_id).first()
    if not trade:
        return

    if pos.direction == "BUY":
        pnl = (close_price - pos.entry_price) * pos.lot_size * 100
    else:
        pnl = (pos.entry_price - close_price) * pos.lot_size * 100

    trade.exit_price = round(close_price, 2)
    trade.pnl = round(pnl, 2)
    trade.status = "closed"
    trade.closed_at = datetime.now(UTC)

    portfolio = _get_portfolio(db)
    portfolio.balance += pnl + trade.spread_cost
    portfolio.total_pnl += pnl
    if pnl > 0:
        portfolio.winning_trades += 1
    else:
        portfolio.losing_trades += 1
    portfolio.updated_at = datetime.now(UTC)

    db.delete(pos)
    db.commit()

    logger.info(f"CLOSED {pos.direction} @ {close_price:.2f} PnL=${pnl:+.2f}")


# --- Poll Loop ---
def _fetch_bars_yfinance(symbol: str = "GC=F", count: int = 200) -> tuple[list, float, float]:
    """Fetch XAUUSD OHLCV bars from yfinance. Returns (bars, bid, ask)."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="10d", interval="15m")
        if df.empty:
            logger.warning("yfinance returned empty data")
            return [], 0, 0

        df = df.tail(count)
        bars = []
        for idx, row in df.iterrows():
            ts = int(idx.timestamp())
            bars.append(
                {
                    "time": ts,
                    "open": round(float(row["Open"]), 5),
                    "high": round(float(row["High"]), 5),
                    "low": round(float(row["Low"]), 5),
                    "close": round(float(row["Close"]), 5),
                    "volume": float(row.get("Volume", 0)),
                }
            )

        last_close = float(df["Close"].iloc[-1])
        spread = 0.3
        bid = round(last_close - spread / 2, 5)
        ask = round(last_close + spread / 2, 5)

        return bars, bid, ask
    except Exception as e:
        logger.error(f"yfinance fetch error: {e}")
        return [], 0, 0


async def _poll_loop():
    logger.info(f"Poll loop started — interval={POLL_INTERVAL}s")
    async with httpx.AsyncClient(timeout=15) as client:
        while True:
            try:
                bars, bid, ask = _fetch_bars_yfinance()
                if not bars:
                    logger.warning("No bars fetched — skipping poll")
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                hour_utc = datetime.now(UTC).hour
                payload = {
                    "bars": bars,
                    "bid": bid,
                    "ask": ask,
                    "hour_utc": hour_utc,
                }

                resp = await client.post(
                    f"{SIGNAL_SERVICE_URL}/api/signal",
                    json=payload,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    current_price = (bid + ask) / 2
                    _check_sl_tp(current_price)

                    direction = data.get("direction", "flat")
                    if direction in ("long", "short"):
                        trade_direction = "BUY" if direction == "long" else "SELL"
                        signal = SignalPayload(
                            symbol=SYMBOL,
                            direction=trade_direction,
                            confidence=data.get("confidence", 0),
                            sl_distance=data.get("sl_distance", 3.0),
                            current_price=data.get("entry_price", current_price),
                            timestamp=data.get("timestamp", ""),
                            features_used=data.get("model_features", 0),
                        )
                        _open_trade(signal)
                    else:
                        logger.info(f"Signal: FLAT (conf={data.get('confidence', 0):.2f})")
                else:
                    logger.warning(f"Signal service returned {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                logger.error(f"Poll error: {e}")
            await asyncio.sleep(POLL_INTERVAL)


# --- API Endpoints ---
@app.get("/health")
def health():
    return {"status": "ok", "service": "paper_executor"}


@app.get("/api/portfolio", response_model=PortfolioResponse)
def get_portfolio():
    with SessionLocal() as db:
        p = _get_portfolio(db)
        open_pos = db.query(PaperPosition).count()
        total = p.total_trades
        win_rate = (p.winning_trades / total * 100) if total > 0 else 0
        equity = p.balance
        if open_pos > 0:
            positions = db.query(PaperPosition).all()
            equity += sum(pos.floating_pnl for pos in positions)
        return PortfolioResponse(
            balance=round(p.balance, 2),
            equity=round(equity, 2),
            total_pnl=round(p.total_pnl, 2),
            total_trades=total,
            winning_trades=p.winning_trades,
            losing_trades=p.losing_trades,
            win_rate=round(win_rate, 1),
            open_positions=open_pos,
        )


@app.get("/api/trades")
def get_trades(limit: int = 50):
    with SessionLocal() as db:
        trades = db.query(PaperTrade).order_by(PaperTrade.id.desc()).limit(limit).all()
        return [
            {
                "id": t.id,
                "symbol": t.symbol,
                "direction": t.direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "sl_distance": t.sl_distance,
                "lot_size": t.lot_size,
                "pnl": t.pnl,
                "spread_cost": t.spread_cost,
                "status": t.status,
                "signal_confidence": t.signal_confidence,
                "opened_at": t.opened_at.isoformat() if t.opened_at else None,
                "closed_at": t.closed_at.isoformat() if t.closed_at else None,
            }
            for t in trades
        ]


@app.get("/api/positions")
def get_positions():
    with SessionLocal() as db:
        pos = db.query(PaperPosition).all()
        return [
            {
                "id": p.id,
                "trade_id": p.trade_id,
                "symbol": p.symbol,
                "direction": p.direction,
                "entry_price": p.entry_price,
                "current_price": p.current_price,
                "sl_price": p.sl_price,
                "tp_price": p.tp_price,
                "lot_size": p.lot_size,
                "floating_pnl": round(p.floating_pnl, 2),
                "opened_at": p.opened_at.isoformat() if p.opened_at else None,
            }
            for p in pos
        ]


@app.post("/api/manual/close")
def manual_close(request: Request):
    _check_auth(request)
    with SessionLocal() as db:
        pos = _get_open_position(db)
        if not pos:
            raise HTTPException(404, "No open position")
        _close_position(pos, pos.current_price or pos.entry_price, db)
        return {"status": "closed", "trade_id": pos.trade_id}


@app.post("/api/poll")
async def manual_poll(request: Request):
    _check_auth(request)
    bars, bid, ask = _fetch_bars_yfinance()
    if not bars:
        return {"error": "Could not fetch price data"}
    hour_utc = datetime.now(UTC).hour
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{SIGNAL_SERVICE_URL}/api/signal",
            json={"bars": bars, "bid": bid, "ask": ask, "hour_utc": hour_utc},
        )
        if resp.status_code == 200:
            data = resp.json()
            current_price = (bid + ask) / 2
            _check_sl_tp(current_price)
            direction = data.get("direction", "flat")
            if direction in ("long", "short"):
                trade_direction = "BUY" if direction == "long" else "SELL"
                signal = SignalPayload(
                    symbol=SYMBOL,
                    direction=trade_direction,
                    confidence=data.get("confidence", 0),
                    sl_distance=data.get("sl_distance", 3.0),
                    current_price=data.get("entry_price", current_price),
                    timestamp=data.get("timestamp", ""),
                    features_used=data.get("model_features", 0),
                )
                result = _open_trade(signal)
                return {"signal": data, "trade": result.model_dump() if result else None}
            return {"signal": data, "trade": None}
        return {"error": f"Signal service {resp.status_code}"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8753)
