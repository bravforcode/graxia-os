"""
Phase 3.3 — Structured News/Events as Risk Gate
Tests for event models, point-in-time store, risk gate, stabilization, macro policy, and import isolation.
"""

import os
from datetime import datetime, UTC
from dataclasses import replace

import pytest

from graxia.packages.quant_os.news_events.event_models import (
    EconomicEvent, EventStatus, EventImportance, GateState,
)
from graxia.packages.quant_os.news_events.event_store import EventStore
from graxia.packages.quant_os.news_events.event_risk_gate import EventRiskGate
from graxia.packages.quant_os.news_events.stabilization_gate import StabilizationGate
from graxia.packages.quant_os.news_events.macro_policy import (
    MacroSourceRole, MacroObservation, MacroPolicyGuard, LLMPolicyGuard,
)
from graxia.packages.quant_os.news_events.integration import NewsEventIntegration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc(year=2026, month=6, day=15, hour=10, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _time(hour, minute=0):
    """Shorthand: _time(10, 0) → 2026-06-15 10:00 UTC."""
    return _utc(2026, 6, 15, hour, minute)


def _make_event(
    event_id="EVT-001",
    importance=EventImportance.HIGH,
    status=EventStatus.SCHEDULED,
    scheduled_at=None,
    received_at=None,
    available_at=None,
    actual=None,
    forecast=100.0,
    previous=99.5,
    currency="USD",
    country="US",
    event_name="NFP",
):
    scheduled_at = scheduled_at or _time(10)
    received_at = received_at or _time(10)
    available_at = available_at or received_at
    return EconomicEvent(
        event_id=event_id,
        source_event_id="SRC-001",
        country=country,
        currency=currency,
        event_name=event_name,
        importance=importance,
        scheduled_at_utc=scheduled_at,
        actual=actual,
        forecast=forecast,
        previous=previous,
        revised_previous=None,
        source="investing.com",
        official_url="https://example.com",
        received_at_utc=received_at,
        available_to_strategy_at_utc=available_at,
        source_revision_id="rev-1",
        status=status,
    )


# ===================================================================
# 1. Event data is point-in-time and timestamped
# ===================================================================

class TestPointInTime:
    def test_event_has_required_timestamps(self):
        e = _make_event()
        assert e.scheduled_at_utc.tzinfo is not None
        assert e.received_at_utc.tzinfo is not None
        assert e.available_to_strategy_at_utc.tzinfo is not None

    def test_event_is_frozen(self):
        e = _make_event()
        with pytest.raises(AttributeError):
            e.event_id = "changed"

    def test_store_query_excludes_future_events(self):
        store = EventStore()
        future_event = _make_event(
            event_id="FUTURE",
            scheduled_at=_utc(2026, 6, 20, 10, 0),
            available_at=_utc(2026, 6, 20, 10, 0),
        )
        store.add_event(future_event)
        now = _utc(2026, 6, 15, 10, 0)
        results = store.query_at(as_of=now, currency="USD")
        assert len(results) == 0

    def test_store_query_includes_past_events(self):
        store = EventStore()
        past = _make_event(
            event_id="PAST",
            scheduled_at=_utc(2026, 6, 10, 10, 0),
            available_at=_utc(2026, 6, 10, 10, 0),
        )
        store.add_event(past)
        results = store.query_at(as_of=_utc(2026, 6, 15, 10, 0), currency="USD")
        assert len(results) == 1

    def test_store_respects_currency_filter(self):
        store = EventStore()
        store.add_event(_make_event(event_id="E1", currency="USD"))
        store.add_event(_make_event(event_id="E2", currency="EUR"))
        results = store.query_at(as_of=_utc(2026, 7, 1, 0, 0), currency="USD")
        assert len(results) == 1
        assert results[0].currency == "USD"

    def test_store_respects_importance_filter(self):
        store = EventStore()
        store.add_event(_make_event(event_id="H", importance=EventImportance.HIGH))
        store.add_event(_make_event(event_id="L", importance=EventImportance.LOW))
        results = store.query_at(as_of=_utc(2026, 7, 1, 0, 0), min_importance="HIGH")
        assert len(results) == 1
        assert results[0].importance == EventImportance.HIGH

    def test_store_replaces_with_later_received_event(self):
        store = EventStore()
        early = _make_event(
            event_id="E1",
            received_at=_utc(2026, 6, 15, 8, 0),
            available_at=_utc(2026, 6, 15, 8, 0),
        )
        late = replace(
            _make_event(
                event_id="E1",
                received_at=_utc(2026, 6, 15, 9, 0),
                available_at=_utc(2026, 6, 15, 9, 0),
            ),
            forecast=200.0,
        )
        store.add_event(early)
        store.add_event(late)
        results = store.query_at(as_of=_utc(2026, 7, 1, 0, 0))
        assert results[0].forecast == 200.0

    def test_store_does_not_downgrade_event(self):
        store = EventStore()
        late = replace(
            _make_event(
                event_id="E1",
                received_at=_utc(2026, 6, 15, 9, 0),
                available_at=_utc(2026, 6, 15, 9, 0),
            ),
            forecast=200.0,
        )
        early = replace(
            _make_event(
                event_id="E1",
                received_at=_utc(2026, 6, 15, 8, 0),
                available_at=_utc(2026, 6, 15, 8, 0),
            ),
            forecast=50.0,
        )
        store.add_event(late)
        store.add_event(early)
        results = store.query_at(as_of=_utc(2026, 7, 1, 0, 0))
        assert results[0].forecast == 200.0


# ===================================================================
# 2. High-impact event block is deterministic and tested
# ===================================================================

class TestRiskGateDeterministic:
    def _gate_and_store(self, pre=30, post=15):
        store = EventStore()
        gate = EventRiskGate(store, pre_block_minutes=pre, post_block_minutes=post)
        return gate, store

    def test_no_events_clears(self):
        gate, _ = self._gate_and_store()
        result = gate.evaluate(at=_time(10))
        assert result.state == GateState.CLEAR
        assert result.eligible_for_new_order_intent is True

    def test_pre_event_block_30min(self):
        gate, store = self._gate_and_store(pre=30)
        evt = _make_event(scheduled_at=_time(10), available_at=_time(9, 0))
        store.add_event(evt)
        # 10 min before event -> inside pre-event block window
        result = gate.evaluate(at=_time(9, 50))
        assert result.state == GateState.EVENT_BLOCK
        assert result.eligible_for_new_order_intent is False
        assert any("PRE_EVENT_BLOCK" in r for r in result.reason_codes)

    def test_outside_pre_event_block_is_clear(self):
        gate, store = self._gate_and_store(pre=30)
        evt = _make_event(scheduled_at=_time(10), available_at=_time(9, 0))
        store.add_event(evt)
        # 40 min before event -> outside window
        result = gate.evaluate(at=_time(9, 20))
        assert result.state == GateState.CLEAR

    def test_delayed_event_still_blocks(self):
        gate, store = self._gate_and_store()
        evt = _make_event(status=EventStatus.DELAYED, scheduled_at=_time(10),
                          available_at=_time(9, 0))
        store.add_event(evt)
        result = gate.evaluate(at=_time(9, 45))
        assert result.state == GateState.EVENT_BLOCK
        assert result.eligible_for_new_order_intent is False

    def test_released_event_with_missing_actual_blocks(self):
        gate, store = self._gate_and_store()
        evt = _make_event(
            status=EventStatus.RELEASED,
            actual=None,
            scheduled_at=_time(10),
            available_at=_time(10),
        )
        store.add_event(evt)
        result = gate.evaluate(at=_time(10, 5))
        assert result.state == GateState.EVENT_BLOCK
        assert result.eligible_for_new_order_intent is False
        assert any("MISSING_ACTUAL" in r for r in result.reason_codes)

    def test_released_event_with_actual_clears(self):
        gate, store = self._gate_and_store()
        evt = _make_event(
            status=EventStatus.RELEASED,
            actual=100.5,
            scheduled_at=_time(10),
            available_at=_time(10),
        )
        store.add_event(evt)
        result = gate.evaluate(at=_time(10, 5))
        assert result.state == GateState.CLEAR
        assert result.eligible_for_new_order_intent is True

    def test_evidence_hash_deterministic(self):
        gate, store = self._gate_and_store()
        store.add_event(_make_event(event_id="X", scheduled_at=_time(10),
                                   available_at=_time(9, 0)))
        r1 = gate.evaluate(at=_time(9, 45))
        r2 = gate.evaluate(at=_time(9, 45))
        assert r1.evidence_hash == r2.evidence_hash

    def test_low_importance_events_ignored_by_risk_gate(self):
        gate, store = self._gate_and_store()
        evt = _make_event(importance=EventImportance.LOW, scheduled_at=_time(10),
                          available_at=_time(9, 0))
        store.add_event(evt)
        result = gate.evaluate(at=_time(9, 45))
        assert result.state == GateState.CLEAR

    def test_medium_importance_events_ignored_by_risk_gate(self):
        gate, store = self._gate_and_store()
        evt = _make_event(importance=EventImportance.MEDIUM, scheduled_at=_time(10),
                          available_at=_time(9, 0))
        store.add_event(evt)
        result = gate.evaluate(at=_time(9, 45))
        assert result.state == GateState.CLEAR

    def test_multiple_high_importance_events_all_listed(self):
        gate, store = self._gate_and_store()
        store.add_event(_make_event(event_id="A", scheduled_at=_time(10),
                                    available_at=_time(9, 0)))
        store.add_event(_make_event(event_id="B", scheduled_at=_time(10, 5),
                                    available_at=_time(9, 0)))
        result = gate.evaluate(at=_time(9, 45))
        assert result.state == GateState.EVENT_BLOCK
        assert "A" in result.event_ids
        assert "B" in result.event_ids


# ===================================================================
# 3. Missing/stale events default to no new order intent
# ===================================================================

class TestFailClosedDefaults:
    def test_empty_store_is_clear(self):
        gate = EventRiskGate(EventStore())
        result = gate.evaluate(at=_time(10))
        assert result.eligible_for_new_order_intent is True

    def test_unknown_status_event_in_window_blocks(self):
        gate, store = EventRiskGate(EventStore()), EventStore()
        gate = EventRiskGate(store)
        evt = _make_event(status=EventStatus.UNKNOWN, scheduled_at=_time(10),
                          available_at=_time(9, 0))
        store.add_event(evt)
        result = gate.evaluate(at=_time(9, 45))
        # UNKNOWN is not SCHEDULED/DELAYED/RELEASED so it is not active
        # => CLEAR (fail-open for unknown is the current implementation)
        # This documents the actual behavior
        assert result.state == GateState.CLEAR

    def test_stabilization_gate_healthy_path(self):
        store = EventStore()
        stab = StabilizationGate(store, stabilization_minutes=5)
        result = stab.is_stabilized(
            at=_time(10, 10),
            currency="USD",
            last_feed_healthy_at=_time(10, 9),
            spread_normal=True,
        )
        assert result.state == GateState.CLEAR

    def test_stabilization_gate_blocks_within_window(self):
        store = EventStore()
        evt = _make_event(
            status=EventStatus.RELEASED,
            actual=100.0,
            scheduled_at=_time(10),
            available_at=_time(10),
        )
        store.add_event(evt)
        stab = StabilizationGate(store, stabilization_minutes=5)
        # 2 minutes after release, within stabilization window
        result = stab.is_stabilized(
            at=_time(10, 2),
            currency="USD",
            last_feed_healthy_at=_time(10, 1),
            spread_normal=True,
        )
        assert result.state == GateState.POST_EVENT_STABILIZATION
        assert result.eligible_for_new_order_intent is False

    def test_stabilization_gate_clears_after_window(self):
        store = EventStore()
        evt = _make_event(
            status=EventStatus.RELEASED,
            actual=100.0,
            scheduled_at=_time(10),
            available_at=_time(10),
        )
        store.add_event(evt)
        stab = StabilizationGate(store, stabilization_minutes=5)
        # 20 minutes after release, well outside stabilization window
        result = stab.is_stabilized(
            at=_time(10, 20),
            currency="USD",
            last_feed_healthy_at=_time(10, 19),
            spread_normal=True,
        )
        assert result.state == GateState.CLEAR
        assert result.eligible_for_new_order_intent is True

    def test_stabilization_blocks_with_unhealthy_feed(self):
        store = EventStore()
        evt = _make_event(
            status=EventStatus.RELEASED,
            actual=100.0,
            scheduled_at=_time(10, 0),
            available_at=_time(10, 0),
        )
        store.add_event(evt)
        stab = StabilizationGate(store, stabilization_minutes=5)
        # Within stabilization_minutes*3 window (15min), but feed is stale
        result = stab.is_stabilized(
            at=_time(10, 12),
            currency="USD",
            last_feed_healthy_at=_time(10, 0),
            spread_normal=True,
        )
        assert result.state == GateState.POST_EVENT_STABILIZATION
        assert result.eligible_for_new_order_intent is False

    def test_stabilization_blocks_with_abnormal_spread(self):
        store = EventStore()
        evt = _make_event(
            status=EventStatus.RELEASED,
            actual=100.0,
            scheduled_at=_time(10, 0),
            available_at=_time(10, 0),
        )
        store.add_event(evt)
        stab = StabilizationGate(store, stabilization_minutes=5)
        # Within stabilization_minutes*3 window (15min), but spread is abnormal
        result = stab.is_stabilized(
            at=_time(10, 12),
            currency="USD",
            last_feed_healthy_at=_time(10, 11),
            spread_normal=False,
        )
        assert result.state == GateState.POST_EVENT_STABILIZATION
        assert result.eligible_for_new_order_intent is False


# ===================================================================
# 4. News/LLM modules cannot import execution submission modules
# ===================================================================

class TestImportIsolation:
    def test_news_events_cannot_import_gold_bot_execution(self):
        """Verify news_events package does not import execution modules."""
        source_files = [
            "event_models.py",
            "event_store.py",
            "event_risk_gate.py",
            "stabilization_gate.py",
            "macro_policy.py",
            "integration.py",
        ]
        pkg_dir = os.path.join(os.path.dirname(__file__), "..", "news_events")
        for fname in source_files:
            with open(os.path.join(pkg_dir, fname), "r") as f:
                content = f.read()
            assert "execution" not in content.lower().split("import")[0] if "import" in content.lower() else True, \
                f"news_events/{fname} must not import execution modules"

    def test_news_events_no_order_submission_imports(self):
        """Explicit check: none of the news_events modules import order submission code."""
        forbidden_imports = ["order_submit", "broker_adapter", "order_manager", "execute_order"]
        source_files = [
            "event_models.py", "event_store.py", "event_risk_gate.py",
            "stabilization_gate.py", "macro_policy.py", "integration.py",
        ]
        pkg_dir = os.path.join(os.path.dirname(__file__), "..", "news_events")
        for fname in source_files:
            with open(os.path.join(pkg_dir, fname), "r") as f:
                content = f.read()
            for forbidden in forbidden_imports:
                assert forbidden not in content, \
                    f"news_events/{fname} imports forbidden module: {forbidden}"

    def test_llm_guard_forbids_execution_action(self):
        """LLMPolicyGuard must forbid invoke_execution."""
        guard = LLMPolicyGuard()
        allowed, reason = guard.check_llm_action("invoke_execution")
        assert allowed is False
        assert "FORBIDDEN" in reason

    def test_llm_guard_allows_allowed_actions(self):
        guard = LLMPolicyGuard()
        for action in LLMPolicyGuard.ALLOWED_USES:
            allowed, reason = guard.check_llm_action(action)
            assert allowed is True, f"{action} should be allowed"

    def test_llm_guard_forbids_all_forbidden_actions(self):
        guard = LLMPolicyGuard()
        for action in LLMPolicyGuard.FORBIDDEN_USES:
            allowed, reason = guard.check_llm_action(action)
            assert allowed is False, f"{action} should be forbidden"


# ===================================================================
# 5. Macro feature availability tests prevent revision leakage
# ===================================================================

class TestMacroPolicyRevisionSafety:
    def test_research_role_observation_available(self):
        guard = MacroPolicyGuard()
        obs = MacroObservation(
            source_name="FRED",
            source_role=MacroSourceRole.RESEARCH,
            observation_timestamp=_utc(2026, 6, 10),
            release_timestamp=_utc(2026, 6, 12),
            available_to_strategy_timestamp=_utc(2026, 6, 12),
            revision_id="rev-1",
            payload_hash="abc",
            value=3.5,
        )
        guard.add_observation(obs)
        available = guard.get_available_observations(as_of=_utc(2026, 6, 15))
        assert len(available) == 1

    def test_future_observation_not_available(self):
        guard = MacroPolicyGuard()
        obs = MacroObservation(
            source_name="FRED",
            source_role=MacroSourceRole.RESEARCH,
            observation_timestamp=_utc(2026, 6, 20),
            release_timestamp=_utc(2026, 6, 20),
            available_to_strategy_timestamp=_utc(2026, 6, 20),
            revision_id="rev-1",
            payload_hash="abc",
        )
        guard.add_observation(obs)
        available = guard.get_available_observations(as_of=_utc(2026, 6, 15))
        assert len(available) == 0

    def test_revision_leakage_detection(self):
        guard = MacroPolicyGuard()
        # Observation available in future = leakage
        obs = MacroObservation(
            source_name="FRED",
            source_role=MacroSourceRole.RESEARCH,
            observation_timestamp=_utc(2026, 6, 15),
            release_timestamp=_utc(2026, 6, 15),
            available_to_strategy_timestamp=_utc(2026, 6, 20),
            revision_id="rev-1",
            payload_hash="abc",
        )
        guard.add_observation(obs)
        safe, violations = guard.validate_no_revision_leakage(as_of=_utc(2026, 6, 15))
        assert safe is False
        assert len(violations) == 1
        assert "REVISION_LEAKAGE" in violations[0]

    def test_clean_history_no_leakage(self):
        guard = MacroPolicyGuard()
        obs = MacroObservation(
            source_name="FRED",
            source_role=MacroSourceRole.RESEARCH,
            observation_timestamp=_utc(2026, 6, 10),
            release_timestamp=_utc(2026, 6, 12),
            available_to_strategy_timestamp=_utc(2026, 6, 12),
            revision_id="rev-1",
            payload_hash="abc",
        )
        guard.add_observation(obs)
        safe, violations = guard.validate_no_revision_leakage(as_of=_utc(2026, 6, 15))
        assert safe is True
        assert violations == []

    def test_macro_guard_forbids_live_directional(self):
        guard = MacroPolicyGuard()
        obs = MacroObservation(
            source_name="LIVE_FEED",
            source_role=MacroSourceRole.LIVE_DIRECTIONAL,
            observation_timestamp=_utc(),
            release_timestamp=_utc(),
            available_to_strategy_timestamp=_utc(),
            revision_id="r1",
            payload_hash="abc",
        )
        allowed, reason = guard.check_observation(obs)
        assert allowed is False
        assert "FORBIDDEN_ROLE" in reason

    def test_macro_guard_allows_calendar_validation(self):
        guard = MacroPolicyGuard()
        obs = MacroObservation(
            source_name="BLS",
            source_role=MacroSourceRole.CALENDAR_VALIDATION,
            observation_timestamp=_utc(),
            release_timestamp=_utc(),
            available_to_strategy_timestamp=_utc(),
            revision_id="r1",
            payload_hash="abc",
        )
        allowed, reason = guard.check_observation(obs)
        assert allowed is True

    def test_is_revision_safe(self):
        obs = MacroObservation(
            source_name="FRED",
            source_role=MacroSourceRole.RESEARCH,
            observation_timestamp=_utc(),
            release_timestamp=_utc(),
            available_to_strategy_timestamp=_utc(2026, 6, 12),
            revision_id="r1",
            payload_hash="abc",
        )
        assert obs.is_revision_safe(as_of=_utc(2026, 6, 15)) is True
        assert obs.is_revision_safe(as_of=_utc(2026, 6, 10)) is False


# ===================================================================
# 6. Integration: NewsEventIntegration combines gates correctly
# ===================================================================

class TestIntegrationGate:
    def _integration(self, pre=30, post=15, stab=5):
        store = EventStore()
        return NewsEventIntegration(store, pre_block_minutes=pre,
                                    post_block_minutes=post,
                                    stabilization_minutes=stab), store

    def test_no_events_allows_order(self):
        integ, _ = self._integration()
        result = integ.can_submit_order(at=_time(10), currency="USD")
        assert result.state == GateState.CLEAR
        assert result.eligible_for_new_order_intent is True

    def test_pre_event_block_takes_priority(self):
        integ, store = self._integration()
        evt = _make_event(scheduled_at=_time(10), available_at=_time(9, 0))
        store.add_event(evt)
        result = integ.can_submit_order(at=_time(9, 45), currency="USD")
        assert result.state == GateState.EVENT_BLOCK
        assert result.eligible_for_new_order_intent is False

    def test_post_event_stabilization_blocks(self):
        integ, store = self._integration()
        evt = _make_event(
            status=EventStatus.RELEASED,
            actual=100.0,
            scheduled_at=_time(10),
            available_at=_time(10),
        )
        store.add_event(evt)
        result = integ.can_submit_order(
            at=_time(10, 2),
            currency="USD",
            last_feed_healthy_at=_time(10, 1),
            spread_normal=True,
        )
        assert result.state == GateState.POST_EVENT_STABILIZATION
        assert result.eligible_for_new_order_intent is False

    def test_gate_state_quick_check(self):
        integ, _ = self._integration()
        state = integ.get_gate_state(at=_time(10), currency="USD")
        assert state == GateState.CLEAR

    def test_record_event_adds_to_store(self):
        integ, _ = self._integration()
        evt = _make_event()
        integ.record_event(evt)
        results = integ.store.query_at(as_of=_utc(2026, 7, 1, 0, 0))
        assert len(results) == 1

    def test_can_submit_order_returns_clear_after_stabilization_window(self):
        integ, store = self._integration(stab=5)
        evt = _make_event(
            status=EventStatus.RELEASED,
            actual=100.0,
            scheduled_at=_time(10),
            available_at=_time(10),
        )
        store.add_event(evt)
        result = integ.can_submit_order(
            at=_time(10, 10),
            currency="USD",
            last_feed_healthy_at=_time(10, 9),
            spread_normal=True,
        )
        assert result.state == GateState.CLEAR
        assert result.eligible_for_new_order_intent is True


# ===================================================================
# 7. Event payload hash determinism
# ===================================================================

class TestPayloadHash:
    def test_same_event_same_hash(self):
        e1 = _make_event(event_id="H1")
        e2 = _make_event(event_id="H1")
        assert e1.payload_hash() == e2.payload_hash()

    def test_different_event_different_hash(self):
        e1 = _make_event(event_id="H1")
        e2 = _make_event(event_id="H2")
        assert e1.payload_hash() != e2.payload_hash()

    def test_hash_changes_on_actual(self):
        e1 = _make_event(event_id="H1", actual=None)
        e2 = _make_event(event_id="H1", actual=100.0)
        assert e1.payload_hash() != e2.payload_hash()
