"""Broker adapter layer for Quant OS"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List
from uuid import uuid4
import random

from ..core.enums import OrderSide, OrderType, OrderStatus, PositionType, CloseReason
from ..core.config import get_config
from ..core.exceptions import BrokerError
from .order import Order


@dataclass
class BrokerPosition:
    """Position representation from broker"""
    symbol: str
    position_type: PositionType
    quantity: Decimal
    avg_price: Decimal
    unrealized_pnl: Decimal = Decimal("0")
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None


@dataclass
class BrokerAccount:
    """Account information from broker"""
    balance: Decimal
    equity: Decimal
    margin: Decimal
    free_margin: Decimal
    margin_level: Decimal
    currency: str = "USD"


@dataclass
class BrokerOrderResponse:
    """Response from broker order submission"""
    success: bool
    broker_order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.CREATED
    filled_quantity: Decimal = Decimal("0")
    avg_fill_price: Optional[Decimal] = None
    fee: Optional[Decimal] = None
    error_message: Optional[str] = None
    raw_response: Optional[Dict] = None


class BrokerAdapter(ABC):
    """Abstract base class for broker adapters"""
    
    def __init__(self, name: str):
        self.name = name
        self.config = get_config()
        self._connected = False
    
    @abstractmethod
    async def connect(self) -> bool:
        """Connect to broker API"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from broker API"""
        pass
    
    @abstractmethod
    async def get_account(self) -> BrokerAccount:
        """Get account information"""
        pass
    
    @abstractmethod
    async def get_positions(self) -> List[BrokerPosition]:
        """Get all positions"""
        pass
    
    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[BrokerPosition]:
        """Get specific position"""
        pass
    
    @abstractmethod
    async def place_order(self, order: Order) -> BrokerOrderResponse:
        """Place an order"""
        pass
    
    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel an order"""
        pass
    
    @abstractmethod
    async def get_order_status(self, broker_order_id: str) -> Optional[BrokerOrderResponse]:
        """Get order status"""
        pass
    
    @abstractmethod
    async def get_price(self, symbol: str) -> Dict[str, Decimal]:
        """Get current price (bid/ask)"""
        pass
    
    @property
    def is_connected(self) -> bool:
        return self._connected


class PaperBroker(BrokerAdapter):
    """
    Paper trading broker adapter - simulates execution.
    
    Features:
    - Realistic slippage (configurable)
    - Commission tracking
    - Partial fills
    - Order delays
    """
    
    def __init__(self):
        super().__init__("PAPER")
        self.prices: Dict[str, Dict[str, Decimal]] = {}
        self.orders: Dict[str, Dict] = {}
        self.positions: Dict[str, BrokerPosition] = {}
        self.account = BrokerAccount(
            balance=Decimal(str(self.config.paper_initial_capital)),
            equity=Decimal(str(self.config.paper_initial_capital)),
            margin=Decimal("0"),
            free_margin=Decimal(str(self.config.paper_initial_capital)),
            margin_level=Decimal("0")
        )
        self.trade_history: List[Dict] = []
    
    async def connect(self) -> bool:
        self._connected = True
        return True
    
    async def disconnect(self) -> None:
        self._connected = False
    
    async def get_account(self) -> BrokerAccount:
        # Update equity based on positions
        unrealized = sum(p.unrealized_pnl for p in self.positions.values())
        self.account.equity = self.account.balance + unrealized
        return self.account
    
    async def get_positions(self) -> List[BrokerPosition]:
        return list(self.positions.values())
    
    async def get_position(self, symbol: str) -> Optional[BrokerPosition]:
        return self.positions.get(symbol)
    
    async def place_order(self, order: Order) -> BrokerOrderResponse:
        """Simulate order execution with realistic fill model"""
        try:
            # Get current price
            price_data = await self.get_price(order.symbol)
            
            if order.side == OrderSide.BUY:
                market_price = price_data["ask"]
            else:
                market_price = price_data["bid"]
            
            # Apply slippage (random 0 to 0.5 pips)
            slippage_pips = Decimal(str(random.uniform(0, float(self.config.paper_slippage_pips))))
            pip_value = Decimal("0.0001") if "JPY" not in order.symbol else Decimal("0.01")
            slippage = slippage_pips * pip_value
            
            if order.side == OrderSide.BUY:
                fill_price = market_price + slippage
            else:
                fill_price = market_price - slippage
            
            # Simulate commission
            lot_size = Decimal(str(getattr(self.config, 'units_per_lot', 100)))
            lots = order.quantity / lot_size
            commission = lots * Decimal(str(self.config.paper_commission_per_lot))
            
            # Record the order
            broker_order_id = f"PAPER_{uuid4().hex[:12]}"
            self.orders[broker_order_id] = {
                "order": order,
                "broker_order_id": broker_order_id,
                "status": OrderStatus.FILLED,
                "filled_quantity": order.quantity,
                "avg_fill_price": fill_price,
                "commission": commission,
                "filled_at": datetime.utcnow()
            }
            
            # Update account
            self.account.balance -= commission
            
            # Update or create position
            await self._update_position(order, fill_price)
            
            return BrokerOrderResponse(
                success=True,
                broker_order_id=broker_order_id,
                status=OrderStatus.FILLED,
                filled_quantity=order.quantity,
                avg_fill_price=fill_price,
                fee=commission,
                raw_response={"slippage_pips": slippage_pips}
            )
            
        except Exception as e:
            return BrokerOrderResponse(
                success=False,
                status=OrderStatus.ERROR,
                error_message=str(e)
            )
    
    async def _update_position(self, order: Order, fill_price: Decimal) -> None:
        """Update position after fill"""
        existing = self.positions.get(order.symbol)
        
        if existing:
            # Calculate new average price
            total_qty = existing.quantity + order.quantity
            avg_price = (
                (existing.avg_price * existing.quantity) + 
                (fill_price * order.quantity)
            ) / total_qty
            
            existing.quantity = total_qty
            existing.avg_price = avg_price
            # Update unrealized P&L
            await self._update_unrealized_pnl(existing)
        else:
            # New position
            pos_type = PositionType.LONG if order.side == OrderSide.BUY else PositionType.SHORT
            self.positions[order.symbol] = BrokerPosition(
                symbol=order.symbol,
                position_type=pos_type,
                quantity=order.quantity,
                avg_price=fill_price,
                stop_loss=order.stop_price if order.order_type == OrderType.STOP else None
            )
    
    async def _update_unrealized_pnl(self, position: BrokerPosition) -> None:
        """Calculate unrealized P&L for position"""
        price_data = await self.get_price(position.symbol)
        
        if position.position_type == PositionType.LONG:
            current_price = price_data["bid"]
            pip_value = Decimal("10") if "JPY" in position.symbol else Decimal("1")
        else:
            current_price = price_data["ask"]
            pip_value = Decimal("10") if "JPY" in position.symbol else Decimal("1")
        
        price_diff = current_price - position.avg_price
        if position.position_type == PositionType.SHORT:
            price_diff = -price_diff
        
        position.unrealized_pnl = price_diff * position.quantity * pip_value
    
    async def cancel_order(self, broker_order_id: str) -> bool:
        if broker_order_id in self.orders:
            self.orders[broker_order_id]["status"] = OrderStatus.CANCELLED
            return True
        return False
    
    async def get_order_status(self, broker_order_id: str) -> Optional[BrokerOrderResponse]:
        order_data = self.orders.get(broker_order_id)
        if not order_data:
            return None
        
        return BrokerOrderResponse(
            success=True,
            broker_order_id=broker_order_id,
            status=order_data["status"],
            filled_quantity=order_data.get("filled_quantity", Decimal("0")),
            avg_fill_price=order_data.get("avg_fill_price")
        )
    
    async def get_price(self, symbol: str) -> Dict[str, Decimal]:
        """Get simulated price for symbol"""
        # In real implementation, this would come from market data feed
        # For paper trading, we use stored prices or generate realistic ones
        if symbol in self.prices:
            return self.prices[symbol]
        
        # Generate realistic prices for major pairs
        base_prices = {
            "EURUSD": Decimal("1.0850"),
            "GBPUSD": Decimal("1.2650"),
            "USDJPY": Decimal("149.50"),
            "AUDUSD": Decimal("0.6550"),
            "USDCAD": Decimal("1.3550"),
            "USDCHF": Decimal("0.8850"),
            "NZDUSD": Decimal("0.6050"),
            "XAUUSD": Decimal("2025.00"),
        }
        
        base = base_prices.get(symbol, Decimal("1.0000"))
        spread_pips = Decimal("0.0001") if "JPY" not in symbol else Decimal("0.01")
        spread = spread_pips * Decimal("1.5")  # 1.5 pip spread
        
        # Add small random movement
        noise = Decimal(str(random.uniform(-0.001, 0.001)))
        
        bid = base + noise
        ask = bid + spread
        
        return {"bid": bid, "ask": ask}
    
    def set_price(self, symbol: str, bid: Decimal, ask: Decimal) -> None:
        """Set price for symbol (for testing or external feed)"""
        self.prices[symbol] = {"bid": bid, "ask": ask}


class MT5BrokerAdapter(BrokerAdapter):
    """
    MetaTrader 5 broker adapter.
    
    Note: Requires MT5 terminal to be running and accessible.
    """
    
    def __init__(self):
        super().__init__("MT5")
        self.mt5 = None
        self.config = get_config()

    def _initialize_kwargs(self) -> dict:
        """Terminal-session-only MT5 initialization contract."""
        self.config.assert_terminal_session_only()
        return {
            "path": self.config.mt5_path,
            "timeout": self.config.mt5_timeout_ms,
        }
    
    async def connect(self) -> bool:
        """Connect to MT5 terminal"""
        try:
            import MetaTrader5 as mt5
            self.mt5 = mt5
            
            # Initialize MT5
            if not self.mt5.initialize(**self._initialize_kwargs()):
                raise BrokerError("MT5 initialization failed", broker="MT5")
            
            # Verify connection
            account_info = self.mt5.account_info()
            if account_info is None:
                raise BrokerError("Failed to get MT5 account info", broker="MT5")
            
            self._connected = True
            return True
            
        except ImportError:
            raise BrokerError("MetaTrader5 package not installed", broker="MT5")
        except Exception as e:
            raise BrokerError(f"MT5 connection failed: {e}", broker="MT5")
    
    async def disconnect(self) -> None:
        if self.mt5:
            self.mt5.shutdown()
            self._connected = False
    
    async def get_account(self) -> BrokerAccount:
        info = self.mt5.account_info()
        if info is None:
            raise BrokerError("Failed to get account info", broker="MT5")
        
        return BrokerAccount(
            balance=Decimal(str(info.balance)),
            equity=Decimal(str(info.equity)),
            margin=Decimal(str(info.margin)),
            free_margin=Decimal(str(info.margin_free)),
            margin_level=Decimal(str(info.margin_level)) if info.margin_level else Decimal("0"),
            currency=info.currency
        )
    
    async def get_positions(self) -> List[BrokerPosition]:
        positions = self.mt5.positions_get()
        if positions is None:
            return []
        
        result = []
        for pos in positions:
            pos_type = PositionType.LONG if pos.type == self.mt5.ORDER_TYPE_BUY else PositionType.SHORT
            result.append(BrokerPosition(
                symbol=pos.symbol,
                position_type=pos_type,
                quantity=Decimal(str(pos.volume)),
                avg_price=Decimal(str(pos.price_open)),
                unrealized_pnl=Decimal(str(pos.profit))
            ))
        
        return result
    
    async def get_position(self, symbol: str) -> Optional[BrokerPosition]:
        positions = await self.get_positions()
        for pos in positions:
            if pos.symbol == symbol:
                return pos
        return None
    
    async def place_order(self, order: Order) -> BrokerOrderResponse:
        """Place order via MT5"""
        try:
            # Map order type
            if order.order_type == OrderType.MARKET:
                mt5_type = self.mt5.ORDER_TYPE_BUY if order.side == OrderSide.BUY else self.mt5.ORDER_TYPE_SELL
            elif order.order_type == OrderType.LIMIT:
                mt5_type = self.mt5.ORDER_TYPE_BUY_LIMIT if order.side == OrderSide.BUY else self.mt5.ORDER_TYPE_SELL_LIMIT
            elif order.order_type == OrderType.STOP:
                mt5_type = self.mt5.ORDER_TYPE_BUY_STOP if order.side == OrderSide.BUY else self.mt5.ORDER_TYPE_SELL_STOP
            else:
                return BrokerOrderResponse(
                    success=False,
                    error_message=f"Unsupported order type: {order.order_type}"
                )
            
            # Build request
            request = {
                "action": self.mt5.TRADE_ACTION_DEAL if order.order_type == OrderType.MARKET else self.mt5.TRADE_ACTION_PENDING,
                "symbol": order.symbol,
                "volume": float(order.quantity),
                "type": mt5_type,
                "price": float(order.price) if order.price else None,
                "sl": float(order.stop_price) if order.stop_price else None,
                "tp": None,  # TODO: Add take profit
                "deviation": 10,  # Slippage in points
                "magic": 234000,  # Expert ID
                "comment": f"QuantOS:{order.strategy_id}",
                "type_time": self.mt5.ORDER_TIME_GTC,
                "type_filling": self.mt5.ORDER_FILLING_IOC,
            }
            
            # Send order
            result = self.mt5.order_send(request)
            
            if result.retcode != self.mt5.TRADE_RETCODE_DONE:
                return BrokerOrderResponse(
                    success=False,
                    error_message=f"MT5 error: {result.retcode} - {result.comment}",
                    raw_response={"retcode": result.retcode, "comment": result.comment}
                )
            
            return BrokerOrderResponse(
                success=True,
                broker_order_id=str(result.order),
                status=OrderStatus.FILLED if order.order_type == OrderType.MARKET else OrderStatus.ACKNOWLEDGED,
                filled_quantity=order.quantity if order.order_type == OrderType.MARKET else Decimal("0"),
                avg_fill_price=Decimal(str(result.price)) if result.price else None,
                raw_response={"retcode": result.retcode, "deal": result.deal, "order": result.order}
            )
            
        except Exception as e:
            return BrokerOrderResponse(
                success=False,
                error_message=str(e)
            )
    
    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            request = {
                "action": self.mt5.TRADE_ACTION_REMOVE,
                "order": int(broker_order_id)
            }
            result = self.mt5.order_send(request)
            return result.retcode == self.mt5.TRADE_RETCODE_DONE
        except Exception:
            return False
    
    async def get_order_status(self, broker_order_id: str) -> Optional[BrokerOrderResponse]:
        try:
            orders = self.mt5.orders_get(ticket=int(broker_order_id))
            if orders and len(orders) > 0:
                order = orders[0]
                return BrokerOrderResponse(
                    success=True,
                    broker_order_id=broker_order_id,
                    status=OrderStatus.ACKNOWLEDGED,  # Simplified
                    raw_response={"type": order.type, "state": order.state}
                )
            return None
        except Exception:
            return None
    
    async def get_price(self, symbol: str) -> Dict[str, Decimal]:
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            raise BrokerError(f"Failed to get price for {symbol}", broker="MT5")
        
        return {
            "bid": Decimal(str(tick.bid)),
            "ask": Decimal(str(tick.ask))
        }


class BrokerManager:
    """Manager for broker failover"""
    
    def __init__(self):
        self.config = get_config()
        self.primary: Optional[BrokerAdapter] = None
        self.fallbacks: List[BrokerAdapter] = []
        self._active: Optional[BrokerAdapter] = None
    
    async def initialize(self) -> bool:
        """Initialize broker connections with failover"""
        # Try primary
        if self.config.primary_broker == "mt5":
            self.primary = MT5BrokerAdapter()
        else:
            self.primary = PaperBroker()  # Default to paper
        
        try:
            if await self.primary.connect():
                self._active = self.primary
                return True
        except Exception:
            pass
        
        # Try fallbacks
        for fallback_name in [self.config.fallback_broker_1, self.config.fallback_broker_2]:
            if fallback_name == "paper":
                fallback = PaperBroker()
            else:
                continue  # Skip unknown brokers
            
            try:
                if await fallback.connect():
                    self._active = fallback
                    self.fallbacks.append(fallback)
                    return True
            except Exception:
                pass
        
        return False
    
    @property
    def active(self) -> BrokerAdapter:
        if self._active is None:
            raise BrokerError("No active broker connection")
        return self._active
    
    async def health_check(self) -> bool:
        """Check if active broker is healthy"""
        try:
            await self.active.get_account()
            return True
        except Exception:
            # Try failover
            return await self._failover()
    
    async def _failover(self) -> bool:
        """Switch to fallback broker"""
        for fallback in self.fallbacks:
            try:
                if await fallback.connect():
                    if self._active:
                        await self._active.disconnect()
                    self._active = fallback
                    return True
            except Exception:
                continue
        return False
