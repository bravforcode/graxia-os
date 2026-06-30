"""Order Manager - orchestrates order lifecycle"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, Callable
import asyncio

from sqlalchemy.orm import Session

from ..core.enums import OrderStatus, TradingMode
from ..core.config import get_config
from ..core.exceptions import (
    RiskViolationError, ComplianceError, DuplicateOrderError,
    KillSwitchTriggeredError, BrokerError
)
from ..core.golden_rules import GOLDEN_RULES
from ..data.models import Order as OrderModel, OrderStateHistory
from .order import Order, OrderStateMachine, create_order
from .idempotency import IdempotencyChecker
from .adapters.base import Order as AdapterOrder
from .adapters.manager import BrokerManager


class OrderManager:
    """
    Central order management system.

    Responsibilities:
    - Order validation
    - Risk check coordination
    - Compliance check coordination
    - Idempotency checking
    - Broker submission
    - State tracking
    - Human approval (MICRO mode)

    The broker layer is provided by the unified adapter hierarchy in
    ``execution/adapters/``.
    """

    def __init__(
        self,
        db_session: Session,
        broker_manager: BrokerManager,
        idempotency_checker: Optional[IdempotencyChecker] = None,
        risk_engine: Optional[Any] = None,
        compliance_gate: Optional[Any] = None,
        kill_switch: Optional[Any] = None
    ):
        self.db = db_session
        self.broker_manager = broker_manager
        self.idempotency = idempotency_checker or IdempotencyChecker(db_session=db_session)
        self.risk_engine = risk_engine
        self.compliance_gate = compliance_gate
        self.kill_switch = kill_switch
        self.config = get_config()

        # Human approval callbacks for MICRO mode
        self._approval_callbacks: Dict[str, Callable] = {}

    async def submit_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        strategy_id: str = "",
        signal_id: Optional[str] = None,
        take_profit: Optional[Decimal] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Submit an order through the full lifecycle.

        Flow:
        1. Check kill switch
        2. Create order object
        3. Check idempotency
        4. Validate
        5. Risk check
        6. Compliance check
        7. Human approval (if MICRO mode)
        8. Submit to broker
        9. Record in database
        """
        try:
            # 1. Check kill switch
            if self.kill_switch and self.kill_switch.is_triggered:
                raise KillSwitchTriggeredError(
                    "Kill switch is active - no new orders allowed",
                    switch_type=self.kill_switch.trigger_type
                )

            # 2. Create order
            from ..core.enums import OrderSide, OrderType
            order = create_order(
                symbol=symbol,
                side=OrderSide(side),
                order_type=OrderType(order_type),
                quantity=quantity,
                price=price,
                stop_price=stop_price,
                strategy_id=strategy_id,
                signal_id=signal_id,
                trading_mode=self.config.trading_mode.value
            )

            # 3. Check idempotency
            self.idempotency.check_and_record(order.idempotency_key, order.id)

            # 4. Create state machine and validate
            state_machine = OrderStateMachine(order)
            state_machine.validate_order()
            state_machine.transition(OrderStatus.VALIDATED, "Order validated")

            # 5. Risk check
            if self.risk_engine:
                risk_result = await self.risk_engine.check_order(order)
                if not risk_result.passed:
                    state_machine.reject(risk_result.reason, "risk_engine")
                    await self._persist_order(order, state_machine)
                    raise RiskViolationError(
                        risk_result.reason,
                        violation_type=risk_result.check_type
                    )
                order.risk_check_id = risk_result.check_id
                state_machine.transition(OrderStatus.RISK_APPROVED, "Risk check passed")

            # 6. Compliance check
            if self.compliance_gate:
                compliance_result = await self.compliance_gate.check(order)
                if not compliance_result.passed:
                    state_machine.reject(compliance_result.reason, "compliance_gate")
                    await self._persist_order(order, state_machine)
                    raise ComplianceError(
                        compliance_result.reason,
                        compliance_check=compliance_result.check_name
                    )
                order.compliance_check_id = compliance_result.check_id
                state_machine.transition(OrderStatus.COMPLIANCE_APPROVED, "Compliance check passed")

            # 7. Human approval for MICRO mode
            if self.config.trading_mode == TradingMode.LIVE_MICRO:
                state_machine.transition(OrderStatus.PENDING_HUMAN, "Awaiting human approval")
                await self._persist_order(order, state_machine)

                # Set expiration timer
                asyncio.create_task(
                    self._expire_order_after_delay(order.id, GOLDEN_RULES.ORDER_EXPIRY_MICRO_SECONDS)
                )

                return {
                    "success": True,
                    "order_id": order.id,
                    "status": OrderStatus.PENDING_HUMAN.value,
                    "message": "Order awaiting human approval (60 second timeout)"
                }

            # 8. Submit to broker
            result = await self._submit_to_broker(order, state_machine)

            # 9. Persist final state
            await self._persist_order(order, state_machine)

            return {
                "success": result["success"],
                "order_id": order.id,
                "broker_order_id": result["broker_order_id"],
                "status": order.status.value,
                "filled_quantity": str(result["filled_quantity"]) if result["filled_quantity"] else None,
                "avg_fill_price": str(result["avg_fill_price"]) if result["avg_fill_price"] else None,
                "fee": str(result["fee"]) if result["fee"] else None,
                "error": result["error_message"]
            }

        except DuplicateOrderError as e:
            return {
                "success": False,
                "error": f"Duplicate order detected: {e.idempotency_key[:16]}...",
                "error_code": "DUPLICATE_ORDER"
            }
        except (RiskViolationError, ComplianceError, KillSwitchTriggeredError) as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.error_code
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": "ORDER_ERROR"
            }

    async def approve_order(self, order_id: str, approver: str) -> Dict[str, Any]:
        """
        Human approval for MICRO mode orders.
        """
        # Get order from database
        db_order = self.db.query(OrderModel).filter(OrderModel.id == order_id).first()
        if not db_order:
            return {"success": False, "error": "Order not found"}

        if db_order.status != OrderStatus.PENDING_HUMAN.value:
            return {"success": False, "error": f"Order not in PENDING_HUMAN state (current: {db_order.status})"}

        # Reconstruct order and state machine
        order = self._reconstruct_order(db_order)
        state_machine = OrderStateMachine(order)

        try:
            # Approve and submit
            state_machine.approve_human(approver)
            result = await self._submit_to_broker(order, state_machine)

            # Update in database
            await self._update_order_in_db(db_order, order)

            return {
                "success": result["success"],
                "order_id": order.id,
                "broker_order_id": result["broker_order_id"],
                "status": order.status.value
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def cancel_order(self, order_id: str, reason: str = "", actor: str = "system") -> Dict[str, Any]:
        """Cancel an order"""
        db_order = self.db.query(OrderModel).filter(OrderModel.id == order_id).first()
        if not db_order:
            return {"success": False, "error": "Order not found"}

        order = self._reconstruct_order(db_order)
        state_machine = OrderStateMachine(order)

        try:
            # Try to cancel with broker if already sent
            if order.status == OrderStatus.SENT_TO_BROKER and order.broker_order_id:
                broker = self.broker_manager.active
                broker.cancel_order(order.broker_order_id)

            state_machine.cancel(reason, actor)
            await self._update_order_in_db(db_order, order)

            return {"success": True, "order_id": order.id, "status": order.status.value}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get order details"""
        db_order = self.db.query(OrderModel).filter(OrderModel.id == order_id).first()
        if not db_order:
            return None

        return {
            "id": str(db_order.id),
            "symbol": db_order.symbol,
            "side": db_order.side,
            "status": db_order.status,
            "quantity": str(db_order.quantity),
            "fill_quantity": str(db_order.fill_quantity),
            "avg_fill_price": str(db_order.avg_fill_price) if db_order.avg_fill_price else None,
            "strategy_id": db_order.strategy_id,
            "created_at": db_order.created_at.isoformat() if db_order.created_at else None,
        }

    def _to_adapter_order(self, order: Order) -> AdapterOrder:
        """Convert the internal Order entity to the canonical adapter order."""
        asset_class = self._asset_class_for_symbol(order.symbol)
        return AdapterOrder(
            order_id=str(order.id),
            signal_id=str(order.signal_id) if order.signal_id else order.client_order_id,
            symbol=order.symbol,
            asset_class=asset_class,
            side=order.side.value,
            quantity=float(order.quantity),
            stop_loss=float(order.stop_price) if order.stop_price else None,
            take_profit=float(order.take_profit) if order.take_profit else None,
        )

    @staticmethod
    def _asset_class_for_symbol(symbol: str) -> str:
        """Map a symbol to the asset class used by the OMS venue router."""
        upper = symbol.upper()
        if "BTC" in upper or "ETH" in upper or "USDT" in upper:
            return "crypto"
        if "XAU" in upper or "XAG" in upper:
            return "metals"
        if upper.startswith("SPX") or upper.startswith("NAS") or upper.startswith("US30"):
            return "indices"
        return "forex"

    async def _submit_to_broker(
        self,
        order: Order,
        state_machine: OrderStateMachine
    ) -> Dict[str, Any]:
        """Submit order to broker via the unified adapter interface."""
        # Health check
        if not await self.broker_manager.health_check():
            raise BrokerError("Broker connection unhealthy")

        broker = self.broker_manager.active

        # Mark as sent
        state_machine.transition(OrderStatus.SENT_TO_BROKER, "Sending to broker")

        # Send order through the canonical sync adapter interface
        adapter_order = self._to_adapter_order(order)
        result = broker.submit_order(adapter_order)

        success = result.status not in (
            OrderStatus.FAILED,
            OrderStatus.TIMEOUT,
            OrderStatus.REJECTED,
        )

        if success:
            order.broker_order_id = result.broker_id

            if result.status == OrderStatus.FILLED:
                # Immediate fill
                state_machine.fill(
                    Decimal(str(result.filled_quantity)),
                    Decimal(str(result.avg_price)) if result.avg_price else Decimal("0"),
                    Decimal(str(result.fee)) if result.fee else Decimal("0"),
                )
            else:
                # Pending / acknowledged / partial — map to the manager state machine
                state_machine.transition(
                    OrderStatus.ACKNOWLEDGED,
                    f"Broker acknowledged: {result.broker_id} (status={result.status.value})",
                )
        else:
            state_machine.reject(result.error or "Broker error", "broker")

        return {
            "success": success,
            "broker_order_id": result.broker_id,
            "status": result.status,
            "filled_quantity": Decimal(str(result.filled_quantity)) if result.filled_quantity else None,
            "avg_fill_price": Decimal(str(result.avg_price)) if result.avg_price else None,
            "fee": Decimal(str(result.fee)) if result.fee else None,
            "error_message": result.error,
        }

    async def _persist_order(self, order: Order, state_machine: OrderStateMachine) -> None:
        """Persist order and state history to database"""
        # Create or update order record
        db_order = self.db.query(OrderModel).filter(OrderModel.id == order.id).first()

        if db_order:
            # Update existing
            await self._update_order_in_db(db_order, order)
        else:
            # Create new
            db_order = OrderModel(
                id=order.id,
                client_order_id=order.client_order_id,
                idempotency_key=order.idempotency_key,
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                quantity=order.quantity,
                price=order.price,
                stop_price=order.stop_price,
                time_in_force=order.time_in_force,
                strategy_id=order.strategy_id,
                signal_id=order.signal_id,
                risk_check_id=order.risk_check_id,
                compliance_check_id=order.compliance_check_id,
                approved_by=order.approved_by,
                trading_mode=order.trading_mode,
                status=order.status,
                fill_quantity=order.fill_quantity,
                avg_fill_price=order.avg_fill_price,
                fee=order.fee,
                created_at=order.created_at,
                updated_at=order.updated_at,
                expires_at=order.expires_at,
                sent_at=order.sent_at,
                filled_at=order.filled_at,
                rejection_reason=order.rejection_reason,
                raw_broker_response=order.raw_broker_response
            )
            self.db.add(db_order)

        # Add state history
        history = OrderStateHistory(
            order_id=order.id,
            from_status=None,  # First state
            to_status=order.status,
            actor="system",
            reason="Order submitted",
            occurred_at=datetime.utcnow()
        )
        self.db.add(history)

        self.db.commit()

    async def _update_order_in_db(self, db_order: OrderModel, order: Order) -> None:
        """Update order record in database"""
        db_order.status = order.status
        db_order.fill_quantity = order.fill_quantity
        db_order.avg_fill_price = order.avg_fill_price
        db_order.fee = order.fee
        db_order.broker_order_id = order.broker_order_id
        db_order.rejection_reason = order.rejection_reason
        db_order.raw_broker_response = order.raw_broker_response
        db_order.updated_at = datetime.utcnow()

        self.db.commit()

    def _reconstruct_order(self, db_order: OrderModel) -> Order:
        """Reconstruct Order object from database record"""
        return Order(
            id=str(db_order.id),
            client_order_id=db_order.client_order_id,
            idempotency_key=db_order.idempotency_key,
            symbol=db_order.symbol,
            side=db_order.side,
            order_type=db_order.order_type,
            quantity=db_order.quantity,
            price=db_order.price,
            stop_price=db_order.stop_price,
            time_in_force=db_order.time_in_force,
            strategy_id=db_order.strategy_id,
            signal_id=str(db_order.signal_id) if db_order.signal_id else None,
            approved_by=db_order.approved_by,
            trading_mode=db_order.trading_mode,
            status=db_order.status,
            fill_quantity=db_order.fill_quantity,
            avg_fill_price=db_order.avg_fill_price,
            fee=db_order.fee,
            broker_order_id=db_order.broker_order_id,
            created_at=db_order.created_at,
            updated_at=db_order.updated_at,
            expires_at=db_order.expires_at,
            sent_at=db_order.sent_at,
            filled_at=db_order.filled_at,
            rejection_reason=db_order.rejection_reason,
            raw_broker_response=db_order.raw_broker_response
        )

    async def _expire_order_after_delay(self, order_id: str, delay_seconds: int) -> None:
        """Expire order after delay if not approved"""
        await asyncio.sleep(delay_seconds)

        db_order = self.db.query(OrderModel).filter(OrderModel.id == order_id).first()
        if db_order and db_order.status == OrderStatus.PENDING_HUMAN.value:
            order = self._reconstruct_order(db_order)
            state_machine = OrderStateMachine(order)
            try:
                state_machine.expire("Human approval timeout")
                await self._update_order_in_db(db_order, order)
            except Exception:
                import logging as _log
                _log.getLogger(__name__).warning(
                    "order_expiry_error", order_id=order_id, exc_info=True
                )
