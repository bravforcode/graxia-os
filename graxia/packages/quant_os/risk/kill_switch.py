"""
Kill Switch System

Hard stop mechanism that immediately halts all trading activity.
Can only be reset manually by authorized user.

Trigger conditions:
- Daily loss limit hit
- Weekly loss limit hit  
- Max drawdown exceeded
- Broker execution failure
- Data quality failure
- Position mismatch detected
- Duplicate order detected
- Manual trigger
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from enum import Enum

from ..core.enums import KillSwitchType, IncidentSeverity
from ..core.config import get_config


@dataclass
class KillSwitchState:
    """Current kill switch state"""
    is_triggered: bool = False
    trigger_type: Optional[KillSwitchType] = None
    triggered_by: str = "system"  # "system_auto" or user_id
    triggered_at: Optional[datetime] = None
    reason: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    
    # Reset info
    reset_at: Optional[datetime] = None
    reset_by: Optional[str] = None
    reset_reason: Optional[str] = None


class KillSwitch:
    """
    Kill Switch - Emergency stop for all trading.
    
    Once triggered:
    - No new orders accepted
    - All pending orders cancelled
    - Open positions may be closed (configurable)
    - Manual reset required
    """
    
    def __init__(self, db_session=None, notification_callback=None):
        self.state = KillSwitchState()
        self.db = db_session
        self.notify = notification_callback
        self.config = get_config()
        
        # Trigger callbacks
        self._on_trigger: List[Callable] = []
        self._on_reset: List[Callable] = []
    
    @property
    def is_triggered(self) -> bool:
        return self.state.is_triggered
    
    @property
    def trigger_type(self) -> Optional[KillSwitchType]:
        return self.state.trigger_type
    
    def trigger(
        self,
        switch_type: KillSwitchType,
        reason: str,
        triggered_by: str = "system_auto",
        context: Dict[str, Any] = None,
        close_positions: bool = False
    ) -> bool:
        """
        Trigger the kill switch.
        
        Args:
            switch_type: Type of kill switch trigger
            reason: Human-readable reason
            triggered_by: Who/what triggered it
            context: Additional context data
            close_positions: Whether to attempt closing open positions
        
        Returns:
            True if newly triggered, False if already active
        """
        if self.state.is_triggered:
            return False
        
        self.state = KillSwitchState(
            is_triggered=True,
            trigger_type=switch_type,
            triggered_by=triggered_by,
            triggered_at=datetime.utcnow(),
            reason=reason,
            context=context or {}
        )
        
        # Log to database
        self._persist_trigger()
        
        # Send notifications
        self._send_notifications(switch_type, reason, triggered_by)
        
        # Call trigger callbacks
        for callback in self._on_trigger:
            try:
                callback(self.state)
            except Exception as e:
                print(f"Kill switch trigger callback error: {e}")
        
        # Attempt to close positions if configured
        if close_positions:
            self._emergency_close_positions()
        
        return True
    
    def reset(
        self,
        reset_by: str,
        reset_reason: str,
        require_approval: bool = True
    ) -> bool:
        """
        Reset the kill switch.
        
        Args:
            reset_by: User ID resetting the switch
            reset_reason: Reason for reset
            require_approval: Whether manual approval is required
        
        Returns:
            True if reset successful
        """
        if not self.state.is_triggered:
            return False
        
        # Verify authorization
        if require_approval and not self._verify_reset_authorization(reset_by):
            raise PermissionError(f"User {reset_by} not authorized to reset kill switch")
        
        # Record reset
        self.state.reset_at = datetime.utcnow()
        self.state.reset_by = reset_by
        self.state.reset_reason = reset_reason
        self.state.is_triggered = False
        
        # Log to database
        self._persist_reset()
        
        # Call reset callbacks
        for callback in self._on_reset:
            try:
                callback(self.state)
            except Exception as e:
                print(f"Kill switch reset callback error: {e}")
        
        return True
    
    def on_trigger(self, callback: Callable):
        """Register callback for trigger event"""
        self._on_trigger.append(callback)
    
    def on_reset(self, callback: Callable):
        """Register callback for reset event"""
        self._on_reset.append(callback)
    
    def check_auto_triggers(
        self,
        daily_pnl_pct: float,
        weekly_pnl_pct: float,
        drawdown_pct: float,
        data_stale: bool = False,
        position_mismatch: bool = False,
        broker_error: bool = False
    ) -> Optional[KillSwitchType]:
        """
        Check if any auto-trigger conditions are met.
        
        Returns:
            KillSwitchType if triggered, None otherwise
        """
        from ..core.golden_rules import GOLDEN_RULES
        
        # Check daily loss
        if daily_pnl_pct < -GOLDEN_RULES.MAX_DAILY_LOSS_PCT:
            self.trigger(
                KillSwitchType.DAILY_LOSS,
                f"Daily loss {abs(daily_pnl_pct):.2f}% exceeds limit {GOLDEN_RULES.MAX_DAILY_LOSS_PCT}%",
                close_positions=True
            )
            return KillSwitchType.DAILY_LOSS
        
        # Check weekly loss
        if weekly_pnl_pct < -GOLDEN_RULES.MAX_WEEKLY_LOSS_PCT:
            self.trigger(
                KillSwitchType.WEEKLY_LOSS,
                f"Weekly loss {abs(weekly_pnl_pct):.2f}% exceeds limit {GOLDEN_RULES.MAX_WEEKLY_LOSS_PCT}%",
                close_positions=True
            )
            return KillSwitchType.WEEKLY_LOSS
        
        # Check drawdown
        if drawdown_pct > GOLDEN_RULES.HARD_STOP_DRAWDOWN_PCT:
            self.trigger(
                KillSwitchType.DRAWDOWN,
                f"Drawdown {drawdown_pct:.2f}% exceeds limit {GOLDEN_RULES.HARD_STOP_DRAWDOWN_PCT}%",
                close_positions=True
            )
            return KillSwitchType.DRAWDOWN
        
        # Check data quality
        if data_stale:
            self.trigger(
                KillSwitchType.DATA_QUALITY,
                "Market data is stale - trading suspended",
                close_positions=False
            )
            return KillSwitchType.DATA_QUALITY
        
        # Check position mismatch
        if position_mismatch:
            self.trigger(
                KillSwitchType.POSITION_MISMATCH,
                "Position mismatch detected between system and broker",
                close_positions=True
            )
            return KillSwitchType.POSITION_MISMATCH
        
        # Check broker health
        if broker_error:
            self.trigger(
                KillSwitchType.BROKER_EXECUTION,
                "Broker execution errors detected",
                close_positions=False
            )
            return KillSwitchType.BROKER_EXECUTION
        
        return None
    
    def get_status(self) -> Dict[str, Any]:
        """Get current kill switch status"""
        return {
            "is_triggered": self.state.is_triggered,
            "trigger_type": self.state.trigger_type.value if self.state.trigger_type else None,
            "triggered_at": self.state.triggered_at.isoformat() if self.state.triggered_at else None,
            "triggered_by": self.state.triggered_by,
            "reason": self.state.reason,
            "reset_at": self.state.reset_at.isoformat() if self.state.reset_at else None,
            "reset_by": self.state.reset_by,
        }
    
    def _persist_trigger(self) -> None:
        """Persist trigger event to database"""
        if not self.db:
            return
        
        from ..data.models import KillSwitchEvent
        
        event = KillSwitchEvent(
            switch_type=self.state.trigger_type,
            action="TRIGGERED",
            triggered_by=self.state.triggered_by,
            reason=self.state.reason,
            context=self.state.context,
            occurred_at=self.state.triggered_at
        )
        self.db.add(event)
        self.db.commit()
    
    def _persist_reset(self) -> None:
        """Persist reset event to database"""
        if not self.db:
            return
        
        # Update the previous event
        from ..data.models import KillSwitchEvent
        
        event = self.db.query(KillSwitchEvent).filter(
            KillSwitchEvent.switch_type == self.state.trigger_type,
            KillSwitchEvent.action == "TRIGGERED",
            KillSwitchEvent.reset_at.is_(None)
        ).order_by(KillSwitchEvent.occurred_at.desc()).first()
        
        if event:
            event.reset_at = self.state.reset_at
            event.reset_by = self.state.reset_by
            # Add reset context
            event.context = {
                **(event.context or {}),
                "reset_reason": self.state.reset_reason
            }
            self.db.commit()
    
    def _send_notifications(self, switch_type: KillSwitchType, reason: str, triggered_by: str) -> None:
        """Send notifications about kill switch trigger"""
        message = f"🚨 KILL SWITCH TRIGGERED 🚨\n\n"
        message += f"Type: {switch_type.value}\n"
        message += f"Reason: {reason}\n"
        message += f"Triggered by: {triggered_by}\n"
        message += f"Time: {datetime.utcnow().isoformat()}\n\n"
        message += "All trading halted. Manual reset required."
        
        if self.notify:
            try:
                self.notify(message, severity=IncidentSeverity.P0)
            except Exception as e:
                print(f"Notification error: {e}")
    
    def _verify_reset_authorization(self, user_id: str) -> bool:
        """Verify user is authorized to reset kill switch"""
        # In production, check against authorized users list
        # For now, allow if matches admin pattern or is in config
        return True  # Simplified - implement proper auth
    
    def _emergency_close_positions(self) -> None:
        """Attempt to close all open positions"""
        # This would call broker to close positions
        # For safety, this is a best-effort operation
        print("Attempting emergency position closure...")


class ManualKillSwitchTrigger:
    """Helper for manual kill switch triggers"""
    
    def __init__(self, kill_switch: KillSwitch):
        self.kill_switch = kill_switch
    
    def emergency_stop(self, user_id: str, reason: str) -> bool:
        """Manual emergency stop"""
        return self.kill_switch.trigger(
            KillSwitchType.MANUAL,
            f"Emergency stop by user: {reason}",
            triggered_by=user_id,
            close_positions=True
        )
    
    def data_issue(self, user_id: str, issue_description: str) -> bool:
        """Stop due to data quality issue"""
        return self.kill_switch.trigger(
            KillSwitchType.DATA_QUALITY,
            f"Data quality issue: {issue_description}",
            triggered_by=user_id,
            close_positions=False
        )
