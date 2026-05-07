"""
graxia/services/revenue_os_api/router.py
Central router — includes all 11 domain routers with consistent prefixes.

URL map:
  POST /api/checkout/stripe-webhook  (public — Stripe signature validated)
  GET  /api/system/readiness         (public — Kubernetes probe)
  GET  /api/system/metrics           (public — Prometheus scrape)
  *    /api/orders/**                (admin auth)
  *    /api/ledger/**                (admin auth)
  *    /api/refunds/**               (admin auth)
  *    /api/entitlements/**          (admin auth)
  *    /api/delivery/**              (admin auth)
  *    /api/campaigns/**             (admin auth)
  *    /api/leads/**                 (admin auth)
  *    /api/emails/**                (admin auth)
  *    /api/approvals/**             (admin auth)
  *    /api/incidents/**             (admin auth)
  *    /api/dashboard/**             (admin auth)
  *    /api/automation/**            (admin auth)

  NEW v12:
  *    /api/bwcp/**                  (admin auth — agent messages)
  *    /api/outbox/**                (admin auth — transactional outbox)
  *    /api/ceo-dashboard/**         (admin auth — executive overview)
"""
from fastapi import APIRouter

from .routers import (
    approvals, automation, bwcp, campaigns, checkout,
    dashboard, delivery, emails, entitlements,
    incidents, leads, ledger, orders, outbox, refunds,
    system, ceo_dashboard,
)

api_router = APIRouter(prefix="/api")

# ── Public (no auth — validated at handler level) ─────────────────────────
api_router.include_router(checkout.router, prefix="/checkout", tags=["Checkout"])
api_router.include_router(system.router,   prefix="/system",   tags=["System"])

# ── Admin (auth enforced per-route via Depends) ────────────────────────────
api_router.include_router(orders.router,       prefix="/orders",       tags=["Orders"])
api_router.include_router(ledger.router,       prefix="/ledger",       tags=["Ledger"])
api_router.include_router(refunds.router,      prefix="/refunds",      tags=["Refunds"])
api_router.include_router(entitlements.router, prefix="/entitlements", tags=["Entitlements"])
api_router.include_router(delivery.router,     prefix="/delivery",     tags=["Delivery"])
api_router.include_router(campaigns.router,    prefix="/campaigns",    tags=["Campaigns"])
api_router.include_router(leads.router,        prefix="/leads",        tags=["Leads"])
api_router.include_router(emails.router,       prefix="/emails",       tags=["Emails"])
api_router.include_router(approvals.router,    prefix="/approvals",    tags=["Approvals"])
api_router.include_router(incidents.router,    prefix="/incidents",    tags=["Incidents"])
api_router.include_router(dashboard.router,    prefix="/dashboard",    tags=["Dashboard"])
api_router.include_router(automation.router,   prefix="/automation",   tags=["Automation"])

# ── NEW v12 Routers ──────────────────────────────────────────────────────
api_router.include_router(bwcp.router,         prefix="/bwcp",         tags=["BWCP Messages"])
api_router.include_router(outbox.router,       prefix="/outbox",       tags=["Outbox Events"])
api_router.include_router(ceo_dashboard.router, prefix="/ceo-dashboard", tags=["CEO Dashboard"])
