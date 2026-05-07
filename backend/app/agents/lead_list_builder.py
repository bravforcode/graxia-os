import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import desc, select

from app.agents.base import BaseAgent
from app.config import settings

logger = logging.getLogger(__name__)


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.I)


class LeadListBuilder(BaseAgent):
    name = "lead_list_builder"

    async def _fetch_html(self, url: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code >= 400:
                    return None
                if "text/html" not in (resp.headers.get("content-type") or ""):
                    return None
                return resp.text
        except Exception:
            return None

    def _candidate_pages(self, base_url: str, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        links: list[str] = []
        for a in soup.select("a[href]"):
            href = str(a.get("href") or "").strip()
            if not href:
                continue
            if href.startswith("mailto:"):
                continue
            absolute = urljoin(base_url, href)
            parsed = urlparse(absolute)
            if parsed.scheme not in {"http", "https"}:
                continue
            if urlparse(base_url).netloc and parsed.netloc != urlparse(base_url).netloc:
                continue
            path = (parsed.path or "").lower()
            if any(k in path for k in ["contact", "about", "team", "people", "leadership", "company"]):
                links.append(absolute)
        dedup = []
        seen = set()
        for item in links:
            if item in seen:
                continue
            seen.add(item)
            dedup.append(item)
        return dedup[:6]

    def _extract_emails(self, html: str) -> list[str]:
        found = {m.group(0).lower() for m in EMAIL_RE.finditer(html or "")}
        cleaned = []
        for email in sorted(found):
            if email.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
                continue
            cleaned.append(email)
        return cleaned[:20]

    async def _extract_from_site(self, site_url: str) -> dict[str, Any]:
        html = await self._fetch_html(site_url)
        if not html:
            return {"site_url": site_url, "emails": []}
        emails = self._extract_emails(html)
        for page in self._candidate_pages(site_url, html):
            page_html = await self._fetch_html(page)
            if not page_html:
                continue
            emails.extend(self._extract_emails(page_html))
        dedup = []
        seen = set()
        for e in emails:
            if e in seen:
                continue
            seen.add(e)
            dedup.append(e)
        return {"site_url": site_url, "emails": dedup[:20]}

    def _split_csv(self, value: str) -> list[str]:
        return [v.strip() for v in (value or "").split(",") if v.strip()]

    def _derive_queries(self) -> list[str]:
        industries = self._split_csv(settings.ICP_INDUSTRIES) or ["SaaS", "e-commerce", "clinic"]
        keywords = self._split_csv(settings.ICP_KEYWORDS) or ["automation", "CRM", "dashboard"]
        queries: list[str] = []
        for industry in industries[:8]:
            for keyword in keywords[:3]:
                queries.append(f"{industry} {keyword} company contact email")
        max_q = max(1, int(settings.LEADGEN_SERPAPI_MAX_QUERIES or 0))
        return queries[:max_q]

    async def _serpapi_sites(self) -> list[str]:
        if not settings.SERPAPI_KEY or not settings.LEADGEN_USE_SERPAPI:
            return []
        sites: list[str] = []
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            for q in self._derive_queries():
                url = "https://serpapi.com/search.json"
                params = {"q": q, "api_key": settings.SERPAPI_KEY, "num": int(settings.LEADGEN_SERPAPI_RESULTS_PER_QUERY or 10), "hl": "en"}
                try:
                    resp = await client.get(url, params=params)
                    if resp.status_code >= 400:
                        continue
                    data = resp.json() or {}
                    for r in data.get("organic_results", []) or []:
                        link = (r.get("link") or "").strip()
                        if not link:
                            continue
                        parsed = urlparse(link)
                        if parsed.scheme not in {"http", "https"}:
                            continue
                        root = f"{parsed.scheme}://{parsed.netloc}"
                        if root not in sites:
                            sites.append(root)
                except Exception:
                    continue
        return sites

    async def run(self) -> dict[str, Any]:
        if not settings.LEADGEN_ENABLED:
            return {"status": "skipped"}

        from app.database import AsyncSessionLocal
        from app.models.contact import Contact

        max_per_run = int(settings.LEADGEN_MAX_PER_RUN or 0)
        max_per_run = max(1, min(max_per_run, 200))

        created = 0
        updated = 0
        exported: list[dict[str, Any]] = []

        export_dir = Path(settings.LEADGEN_EXPORT_DIR)
        export_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        export_path = export_dir / f"leads_{ts}.json"

        async with AsyncSessionLocal() as db:
            sites = await self._serpapi_sites()
            for company_site in sites:
                if created >= max_per_run:
                    break
                extracted = await self._extract_from_site(company_site)
                domain = urlparse(company_site).netloc.lower()
                if domain.startswith("www."):
                    domain = domain[4:]
                for email in extracted.get("emails", []):
                    existing = (
                        await db.execute(
                            select(Contact)
                            .where(Contact.is_deleted.is_(False))
                            .where(Contact.email == email)
                            .limit(1)
                        )
                    ).scalar_one_or_none()
                    if existing:
                        updated += 1
                        continue
                    lead = Contact(
                        id=uuid4(),
                        name=domain,
                        email=email,
                        company=domain,
                        role="Unknown",
                        contact_type="lead",
                        value_score=5,
                        notes=f"Source: serpapi_site {company_site}",
                    )
                    db.add(lead)
                    created += 1
                    exported.append(
                        {
                            "name": lead.name,
                            "email": lead.email,
                            "company": lead.company,
                            "role": lead.role,
                            "source": "serpapi",
                            "source_url": company_site,
                            "confidence": 0.55,
                        }
                    )
                    if created >= max_per_run:
                        break

            candidates = list(
                (
                    await db.execute(
                        select(Contact)
                        .where(Contact.is_deleted.is_(False))
                        .where(Contact.linkedin_url.is_not(None))
                        .where(Contact.linkedin_url != "")
                        .order_by(desc(Contact.value_score), Contact.created_at.desc())
                        .limit(max_per_run)
                    )
                )
                .scalars()
                .all()
            )

            for row in candidates:
                url = (row.linkedin_url or "").strip()
                parsed = urlparse(url)
                if not parsed.scheme:
                    continue
                domain = parsed.netloc.lower()
                if domain.startswith("www."):
                    domain = domain[4:]
                company_site = f"{parsed.scheme}://{parsed.netloc}"
                extracted = await self._extract_from_site(company_site)
                for email in extracted.get("emails", []):
                    existing = (
                        await db.execute(
                            select(Contact)
                            .where(Contact.is_deleted.is_(False))
                            .where(Contact.email == email)
                            .limit(1)
                        )
                    ).scalar_one_or_none()
                    if existing:
                        updated += 1
                        continue
                    lead = Contact(
                        id=uuid4(),
                        name=row.company or domain,
                        email=email,
                        company=row.company or domain,
                        role=row.role or "Unknown",
                        contact_type="lead",
                        value_score=row.value_score or 5,
                        notes=f"Source: company_site {company_site}",
                    )
                    db.add(lead)
                    created += 1
                    exported.append(
                        {
                            "name": lead.name,
                            "email": lead.email,
                            "company": lead.company,
                            "role": lead.role,
                            "source": "company_site",
                            "source_url": company_site,
                            "confidence": 0.6,
                        }
                    )
                    if created >= max_per_run:
                        break
                if created >= max_per_run:
                    break

            await db.commit()

        import json

        export_path.write_text(json.dumps(exported, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "ok", "created": created, "updated": updated, "export_path": str(export_path)}


lead_list_builder_agent = LeadListBuilder()
