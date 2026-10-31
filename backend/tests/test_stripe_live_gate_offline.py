"""Offline regression checks for Stripe write gating."""

import os
import sys
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, main
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Import with a harmless key so this executable never reads a configured key.
with patch.dict(
    os.environ,
    {
        "STRIPE_SECRET_KEY": "sk_test_offline_mock_key",
        "ALLOW_LIVE_STRIPE": "false",
    },
):
    from app.core import stripe_client


async def create_checkout_session():
    return await stripe_client.create_stripe_checkout_session(
        customer_id=None,
        success_url="https://example.test/success",
        cancel_url="https://example.test/cancel",
        line_items=[{"price": "price_offline_mock"}],
        metadata={"offline": "true"},
    )


STRIPE_WRITE_CALLS = (
    (
        "customer.create",
        stripe_client.stripe.Customer,
        "create",
        lambda: stripe_client.create_stripe_customer(
            email="offline@example.test", name="Offline", org_id="org-offline"
        ),
    ),
    (
        "subscription.create",
        stripe_client.stripe.Subscription,
        "create",
        lambda: stripe_client.create_stripe_subscription(
            customer_id="cus_offline", price_id="price_offline"
        ),
    ),
    (
        "subscription.cancel",
        stripe_client.stripe.Subscription,
        "cancel",
        lambda: stripe_client.cancel_stripe_subscription("sub_offline"),
    ),
    (
        "checkout.create",
        stripe_client.stripe.checkout.Session,
        "create",
        create_checkout_session,
    ),
    (
        "portal.create",
        stripe_client.stripe.billing_portal.Session,
        "create",
        lambda: stripe_client.get_portal_url(
            "cus_offline", "https://example.test/return"
        ),
    ),
)


class StripeLiveGateOfflineTests(IsolatedAsyncioTestCase):
    async def test_live_keys_block_before_provider_when_consent_is_false_or_missing(self):
        for key in ("sk_live_offline_mock_key", "rk_live_offline_mock_key"):
            for consent in (False, None):
                with self.subTest(key=key[:2], consent=consent):
                    values = {"STRIPE_SECRET_KEY": key, "STRIPE_ENABLE_PROMPTPAY": False}
                    if consent is not None:
                        values["ALLOW_LIVE_STRIPE"] = consent

                    with (
                        patch.object(
                            stripe_client, "settings", SimpleNamespace(**values)
                        ),
                        patch.object(
                            stripe_client.stripe.checkout.Session, "create"
                        ) as provider_create,
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError, "Live Stripe Checkout is disabled"
                        ):
                            await create_checkout_session()
                        provider_create.assert_not_called()

    async def test_every_provider_write_blocks_live_keys_without_explicit_consent(
        self,
    ):
        for key in ("sk_live_offline_mock_key", "rk_live_offline_mock_key"):
            for consent in (False, None):
                values = {
                    "STRIPE_SECRET_KEY": key,
                    "STRIPE_ENABLE_PROMPTPAY": False,
                }
                if consent is not None:
                    values["ALLOW_LIVE_STRIPE"] = consent
                with self.subTest(key=key[:2], consent=consent):
                    with patch.object(
                        stripe_client, "settings", SimpleNamespace(**values)
                    ):
                        with ExitStack() as stack:
                            providers = {
                                name: stack.enter_context(
                                    patch.object(target, method)
                                )
                                for name, target, method, _call in STRIPE_WRITE_CALLS
                            }
                            for name, _target, _method, call in STRIPE_WRITE_CALLS:
                                with self.subTest(operation=name):
                                    with self.assertRaisesRegex(
                                        RuntimeError, "Live Stripe"
                                    ):
                                        await call()
                            for provider in providers.values():
                                provider.assert_not_called()

    async def test_every_provider_write_blocks_unknown_or_missing_keys(self):
        for key in (
            "",
            "pk_test_not_a_secret",
            "sk_unknown_offline_key",
            "sk_test",
            "rk_test",
            "sk_test_",
            "rk_test_",
        ):
            with self.subTest(key=key[:2]):
                with patch.object(
                    stripe_client,
                    "settings",
                    SimpleNamespace(
                        STRIPE_SECRET_KEY=key,
                        STRIPE_ENABLE_PROMPTPAY=False,
                        ALLOW_LIVE_STRIPE=True,
                    ),
                ):
                    with ExitStack() as stack:
                        providers = {
                            name: stack.enter_context(patch.object(target, method))
                            for name, target, method, _call in STRIPE_WRITE_CALLS
                        }
                        for name, _target, _method, call in STRIPE_WRITE_CALLS:
                            with self.subTest(operation=name):
                                with self.assertRaisesRegex(
                                    RuntimeError, "Stripe writes"
                                ):
                                    await call()
                        for provider in providers.values():
                            provider.assert_not_called()

    async def test_every_provider_write_allows_test_keys_with_mocked_provider(self):
        for key in (
            "sk_test_offline_mock_key",
            "rk_test_offline_mock_key",
        ):
            with self.subTest(key=key[:2]):
                with patch.object(
                    stripe_client,
                    "settings",
                    SimpleNamespace(
                        STRIPE_SECRET_KEY=key,
                        STRIPE_ENABLE_PROMPTPAY=False,
                        ALLOW_LIVE_STRIPE=False,
                    ),
                ):
                    with ExitStack() as stack:
                        providers = {
                            name: stack.enter_context(patch.object(target, method))
                            for name, target, method, _call in STRIPE_WRITE_CALLS
                        }
                        for name, _target, _method, call in STRIPE_WRITE_CALLS:
                            with self.subTest(operation=name):
                                expected = SimpleNamespace(
                                    url=f"https://example.test/{name}"
                                )
                                providers[name].return_value = expected
                                result = await call()
                                if name == "portal.create":
                                    self.assertEqual(result, expected.url)
                                else:
                                    self.assertIs(result, expected)
                                providers[name].assert_called_once()

    async def test_every_provider_write_allows_live_keys_only_with_consent(self):
        for key in ("sk_live_offline_mock_key", "rk_live_offline_mock_key"):
            with self.subTest(key=key[:2]):
                with patch.object(
                    stripe_client,
                    "settings",
                    SimpleNamespace(
                        STRIPE_SECRET_KEY=key,
                        STRIPE_ENABLE_PROMPTPAY=False,
                        ALLOW_LIVE_STRIPE=True,
                    ),
                ):
                    with ExitStack() as stack:
                        providers = {
                            name: stack.enter_context(patch.object(target, method))
                            for name, target, method, _call in STRIPE_WRITE_CALLS
                        }
                        for name, _target, _method, call in STRIPE_WRITE_CALLS:
                            with self.subTest(operation=name):
                                expected = SimpleNamespace(
                                    url=f"https://example.test/{name}"
                                )
                                providers[name].return_value = expected
                                result = await call()
                                if name == "portal.create":
                                    self.assertEqual(result, expected.url)
                                else:
                                    self.assertIs(result, expected)
                                providers[name].assert_called_once()

    async def test_test_mode_keys_call_only_the_mocked_provider(self):
        for key in ("sk_test_offline_mock_key", "rk_test_offline_mock_key"):
            with self.subTest(key=key[:2]):
                expected = object()
                with (
                    patch.object(
                        stripe_client,
                        "settings",
                        SimpleNamespace(
                            STRIPE_SECRET_KEY=key,
                            STRIPE_ENABLE_PROMPTPAY=False,
                            ALLOW_LIVE_STRIPE=False,
                        ),
                    ),
                    patch.object(
                        stripe_client.stripe.checkout.Session, "create"
                    ) as provider_create,
                ):
                    provider_create.return_value = expected
                    result = await create_checkout_session()
                    self.assertIs(result, expected)
                    provider_create.assert_called_once()

    async def test_live_keys_call_only_the_mocked_provider_when_explicitly_enabled(
        self,
    ):
        for key in ("sk_live_offline_mock_key", "rk_live_offline_mock_key"):
            with self.subTest(key=key[:2]):
                expected = object()
                with (
                    patch.object(
                        stripe_client,
                        "settings",
                        SimpleNamespace(
                            STRIPE_SECRET_KEY=key,
                            STRIPE_ENABLE_PROMPTPAY=False,
                            ALLOW_LIVE_STRIPE=True,
                        ),
                    ),
                    patch.object(
                        stripe_client.stripe.checkout.Session, "create"
                    ) as provider_create,
                ):
                    provider_create.return_value = expected
                    result = await create_checkout_session()
                    self.assertIs(result, expected)
                    provider_create.assert_called_once()


if __name__ == "__main__":
    main()
