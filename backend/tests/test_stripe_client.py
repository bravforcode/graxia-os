"""Offline regression tests for Stripe SDK thread offloading."""

import asyncio
import os
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Import with a harmless test key; each SDK operation below is also mocked.
with patch.dict(
    os.environ,
    {
        "STRIPE_SECRET_KEY": "sk_test_offline_mock_key",
        "ALLOW_LIVE_STRIPE": "false",
    },
):
    from app.core import stripe_client


class StripeClientThreadOffloadTests(unittest.IsolatedAsyncioTestCase):
    async def assert_sdk_call_is_offloaded(
        self,
        operation,
        target,
        method,
        invoke,
        expected_args,
        expected_kwargs,
        sdk_result,
        expected_result,
    ):
        event_loop_thread = threading.current_thread()
        sdk_started = threading.Event()
        event_loop_resumed = threading.Event()
        sdk_threads = []

        def blocking_sdk_call(*args, **kwargs):
            sdk_threads.append(threading.current_thread())
            sdk_started.set()
            if not event_loop_resumed.wait(timeout=0.5):
                raise AssertionError(
                    f"event loop stalled during blocking {operation} call"
                )
            return sdk_result

        test_settings = SimpleNamespace(
            STRIPE_SECRET_KEY="sk_test_offline_mock_key",
            ALLOW_LIVE_STRIPE=False,
            STRIPE_ENABLE_PROMPTPAY=False,
        )
        with (
            patch.object(stripe_client, "settings", test_settings),
            patch.object(target, method, side_effect=blocking_sdk_call) as sdk_call,
        ):
            task = asyncio.create_task(invoke())
            await asyncio.wait_for(asyncio.to_thread(sdk_started.wait), timeout=1)
            event_loop_resumed.set()
            result = await asyncio.wait_for(task, timeout=1)

        self.assertEqual(result, expected_result)
        self.assertEqual(len(sdk_threads), 1)
        self.assertIsNot(sdk_threads[0], event_loop_thread)
        sdk_call.assert_called_once_with(*expected_args, **expected_kwargs)

    async def test_all_sdk_calls_are_offloaded_and_preserve_arguments(self):
        customer = object()
        subscription = object()
        checkout_session = object()
        portal_session = SimpleNamespace(url="https://example.test/portal")
        cases = (
            (
                "customer.create",
                stripe_client.stripe.Customer,
                "create",
                lambda: stripe_client.create_stripe_customer(
                    "offline@example.test", "Offline", "org_offline"
                ),
                (),
                {
                    "email": "offline@example.test",
                    "name": "Offline",
                    "metadata": {
                        "organization_id": "org_offline",
                        "source": "graxia",
                    },
                },
                customer,
                customer,
            ),
            (
                "subscription.create",
                stripe_client.stripe.Subscription,
                "create",
                lambda: stripe_client.create_stripe_subscription(
                    "cus_offline", "price_offline", trial_days=7
                ),
                (),
                {
                    "customer": "cus_offline",
                    "items": [{"price": "price_offline"}],
                    "trial_period_days": 7,
                    "payment_behavior": "default_incomplete",
                    "expand": ["latest_invoice.payment_intent"],
                },
                subscription,
                subscription,
            ),
            (
                "subscription.cancel",
                stripe_client.stripe.Subscription,
                "cancel",
                lambda: stripe_client.cancel_stripe_subscription("sub_offline"),
                ("sub_offline",),
                {},
                subscription,
                subscription,
            ),
            (
                "checkout.create",
                stripe_client.stripe.checkout.Session,
                "create",
                lambda: stripe_client.create_stripe_checkout_session(
                    customer_id=None,
                    success_url="https://example.test/success",
                    cancel_url="https://example.test/cancel",
                    line_items=[{"price": "price_offline"}],
                    metadata={"offline": "true"},
                    customer_email="offline@example.test",
                ),
                (),
                {
                    "mode": "payment",
                    "success_url": "https://example.test/success",
                    "cancel_url": "https://example.test/cancel",
                    "line_items": [{"price": "price_offline"}],
                    "metadata": {"offline": "true"},
                    "customer_email": "offline@example.test",
                },
                checkout_session,
                checkout_session,
            ),
            (
                "portal.create",
                stripe_client.stripe.billing_portal.Session,
                "create",
                lambda: stripe_client.get_portal_url(
                    "cus_offline", "https://example.test/return"
                ),
                (),
                {
                    "customer": "cus_offline",
                    "return_url": "https://example.test/return",
                },
                portal_session,
                portal_session.url,
            ),
        )

        for case in cases:
            with self.subTest(operation=case[0]):
                await self.assert_sdk_call_is_offloaded(*case)


if __name__ == "__main__":
    unittest.main()
