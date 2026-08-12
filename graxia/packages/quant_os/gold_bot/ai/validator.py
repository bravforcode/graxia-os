"""
Claude AI Signal Validator
Uses AsyncAnthropic for non-blocking signal validation.

Before: sync client + ThreadPoolExecutor → thread leak on timeout
After: AsyncAnthropic + asyncio.wait_for → proper cancellation
"""

import asyncio
import os
from typing import Optional
from datetime import datetime

from ..core.engine import AggregatedSignal, SignalDirection
from ..core.config import BotConfig


class ClaudeAIValidator:
    """
    Uses Claude AI to validate trading signals.
    
    Uses AsyncAnthropic for native async — no thread pool needed.
    asyncio.wait_for cancels the task properly on timeout.
    """

    def __init__(self, config: BotConfig):
        self.config = config
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self._client = None  # Lazy init — reused across calls

    def _get_client(self):
        """Lazy-init AsyncAnthropic client (reused across calls)"""
        if self._client is None and self.api_key:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(api_key=self.api_key)
        return self._client

    async def validate(self, signal: AggregatedSignal) -> bool:
        """
        Validate a signal using Claude AI.
        
        Returns True if approved, False if rejected or on error.
        """
        if not self.config.ai_validation_enabled:
            return True

        if not self.api_key:
            # No AI key — approve high-confidence signals
            return signal.total_score >= self.config.min_score_to_trade * 1.2

        try:
            client = self._get_client()
            if client is None:
                return False

            prompt = self._build_prompt(signal)

            # Native async call — asyncio.wait_for cancels properly
            message = await asyncio.wait_for(
                client.messages.create(
                    model=self.config.ai_model,
                    max_tokens=500,
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=5.0,
            )

            response = message.content[0].text if message.content else ""
            return self._parse_response(response)

        except asyncio.TimeoutError:
            # Real cancellation — no orphan thread
            return False
        except Exception as e:
            print(f"  AI validation error: {e}")
            return False

    def _build_prompt(self, signal: AggregatedSignal) -> str:
        """Build validation prompt for Claude"""
        strategy_scores = []
        for s in signal.signals:
            strategy_scores.append(
                f"  - {s.strategy_name}: {s.score}% ({s.direction.value}) - {s.reasoning}"
            )

        prompt = f"""You are a professional gold (XAUUSD) trading analyst. Validate this trading signal.

SIGNAL DETAILS:
- Direction: {signal.direction.value}
- Total Score: {signal.total_score}/1000
- Active Strategies: {signal.active_strategies}/13
- Buy Score: {signal.buy_score}
- Sell Score: {signal.sell_score}

ENTRY LEVELS:
- Entry: {signal.consensus_entry:.2f}
- Stop Loss: {signal.consensus_sl:.2f}
- Take Profit: {signal.consensus_tp:.2f}

STRATEGY SCORES:
{chr(10).join(strategy_scores)}

CONTEXT:
- Symbol: XAUUSD (Gold)
- Timeframe: M15
- Current time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

RULES:
1. Only approve if risk/reward is at least 1:2
2. Reject if too many conflicting signals
3. Reject if score is borderline
4. Consider current market conditions

Respond with ONLY:
APPROVE: [brief reason]
or
REJECT: [brief reason]"""

        return prompt

    def _parse_response(self, response: str) -> bool:
        """Parse Claude's response"""
        response_upper = response.upper()

        if "APPROVE" in response_upper:
            return True
        elif "REJECT" in response_upper:
            return False

        # Default: reject if unclear
        return False
