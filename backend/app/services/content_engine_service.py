"""Content engine services: AI writer, keyword research, affiliate injection."""
import asyncio
import hashlib
import json
import re
from decimal import Decimal
from typing import Any

from app.ai.client import AIClient
from app.ai.models import ChatMessage, MessageRole

# ---------------------------------------------------------------------------
# Keyword research templates (programmatic SEO)
# ---------------------------------------------------------------------------

KEYWORD_TEMPLATES = {
    "site_a": {
        "review": [
            "{tool} review",
            "{tool} review 2025",
            "is {tool} worth it",
            "{tool} honest review",
        ],
        "comparison": [
            "{tool_a} vs {tool_b}",
            "{tool_a} vs {tool_b} 2025",
            "best alternative to {tool}",
            "{tool} alternatives",
        ],
        "howto": [
            "how to use {tool}",
            "how to make money with {tool}",
            "{tool} tutorial for beginners",
            "{tool} guide 2025",
        ],
        "best": [
            "best {category} 2025",
            "best {category} for beginners",
            "top 10 {category}",
            "best free {category}",
        ],
    },
    "site_b": {
        "review": [
            "รีวิว {product}",
            "{product} ดีไหม",
            "{product} รีวิวจริง",
        ],
        "howto": [
            "วิธี{action}ด้วย {product}",
            "{product} ใช้ยังไง",
            "สอนใช้ {product}",
        ],
        "best": [
            "{category} ที่ดีที่สุด 2025",
            "{category} แนะนำ",
            "{category} ยอดนิยม",
        ],
    },
}

SITE_A_TOOLS = [
    "ChatGPT", "Claude AI", "Gemini", "Jasper AI", "Copy.ai",
    "Midjourney", "DALL-E", "Stable Diffusion", "Perplexity AI",
    "Notion AI", "Grammarly", "Writesonic", "Semrush", "Ahrefs",
]

SITE_A_CATEGORIES = [
    "AI writing tools", "SEO tools", "AI image generators",
    "keyword research tools", "content creation tools",
]

SITE_B_PRODUCTS = [
    "อาหารเสริมลดน้ำหนัก", "โปรตีน", "วิตามินรวม",
    "คอลลาเจน", "โอเมก้า 3", "ไซตี้",
]

SITE_B_ACTIONS = [
    "ลดน้ำหนัก", "เพิ่มกล้ามเนื้อ", "ดูแลผิว", "บำรุงสุขภาพ",
]

SITE_B_CATEGORIES = [
    "อาหารเสริม", "อาหารคลีน", "โปรแกรมออกกำลังกาย",
    "วิธีลดน้ำหนัก", "อาหารสุขภาพ",
]


async def generate_article_outline(
    keyword: str,
    site: str,
    language: str,
    content_type: str = "article",
    word_count: int = 2000,
) -> dict[str, Any]:
    """Generate a structured article outline using the AI client."""
    client = AIClient()

    system_prompt = (
        "You are an expert SEO content strategist with 10+ years experience. "
        "Create a detailed, conversion-optimized article outline. "
        "Return ONLY valid JSON — no markdown, no explanation."
    )

    user_prompt = f"""
Keyword: {keyword}
Language: {language}
Site Type: {site}
Content Type: {content_type}
Target Length: {word_count} words

Return JSON structure:
{{
  "title": "SEO-optimized H1 title (60 chars max)",
  "meta_description": "155-char meta description with keyword",
  "slug": "url-friendly-slug",
  "sections": [
    {{
      "heading": "H2 heading text",
      "type": "intro|body|comparison|list|faq|conclusion",
      "word_count": 200,
      "subheadings": ["H3 text"]
    }}
  ],
  "faq": [
    {{"q": "question", "a": "brief answer"}}
  ],
  "affiliate_opportunities": ["slug1", "slug2"],
  "schema_type": "Article|HowTo|FAQPage|Review",
  "lsi_keywords": ["related term 1", "related term 2"]
}}
"""

    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
        ChatMessage(role=MessageRole.USER, content=user_prompt),
    ]

    result = await client.chat(
        messages=messages,
        temperature=0.75,
        max_tokens=4000,
        task_type="analysis",
    )

    raw = result.get("content", "")
    # Extract JSON from potential markdown fences
    cleaned = re.sub(r"^```json\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    outline = json.loads(cleaned)
    return outline


async def write_article_section(
    keyword: str,
    heading: str,
    section_type: str,
    word_count: int,
    language: str,
    site: str,
    lsi_keywords: list[str],
) -> str:
    """Write a single article section using the AI client."""
    client = AIClient()

    system_prompt = (
        f"You are a professional content writer specializing in {site} content. "
        "Write naturally, helpfully, and with genuine expertise. "
        "Rules:\n"
        "- Never mention AI wrote this\n"
        "- No fluff — every sentence must add value\n"
        "- Include specific examples, numbers, or real-world applications\n"
        f"- Language: {language} (if Thai, write authentic Thai, NOT Google Translate)\n"
        "- Aim for E-E-A-T signals (Experience, Expertise, Authoritativeness, Trust)"
    )

    user_prompt = f"""
Article topic: {keyword}
Section to write: {heading}
Section type: {section_type}
Target word count: {word_count}
LSI keywords to naturally include: {', '.join(lsi_keywords[:5])}

Write this section now:
"""

    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
        ChatMessage(role=MessageRole.USER, content=user_prompt),
    ]

    result = await client.chat(
        messages=messages,
        temperature=0.7,
        max_tokens=3000,
        task_type="chat",
    )

    return result.get("content", "")


async def generate_full_article(
    keyword: str,
    site: str,
    language: str = "en",
    content_type: str = "article",
    word_count: int = 2000,
) -> dict[str, Any]:
    """Full pipeline: outline → parallel sections → assemble → affiliate inject."""
    # Step 1: Generate outline
    outline = await generate_article_outline(
        keyword=keyword, site=site, language=language,
        content_type=content_type, word_count=word_count,
    )

    sections = outline.get("sections", [])
    lsi_keywords = outline.get("lsi_keywords", [])

    # Step 2: Write all sections in parallel
    tasks = []
    for section in sections:
        tasks.append(
            write_article_section(
                keyword=keyword,
                heading=section["heading"],
                section_type=section.get("type", "body"),
                word_count=section.get("word_count", 300),
                language=language,
                site=site,
                lsi_keywords=lsi_keywords,
            )
        )

    section_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Step 3: Assemble
    assembled_sections = []
    for i, (section, result) in enumerate(zip(sections, section_results)):
        if isinstance(result, Exception):
            content = f"<!-- Section generation failed: {section['heading']} -->\n"
        else:
            content = result

        if section.get("type") == "intro":
            assembled_sections.append(content)
        else:
            assembled_sections.append(f"## {section['heading']}\n\n{content}")

    full_content = "\n\n".join(assembled_sections)

    # Step 4: Add FAQ
    faq_items = outline.get("faq", [])
    if faq_items:
        faq_md = "\n\n## FAQ\n\n"
        for item in faq_items:
            faq_md += f"**Q: {item['q']}**\n\nA: {item['a']}\n\n"
        full_content += faq_md

    # Step 5: Affiliate injection (best-effort, no DB dependency at generation time)
    affiliate_suggestions = outline.get("affiliate_opportunities", [])
    full_content = inject_affiliate_links(full_content, site, affiliate_suggestions)

    actual_word_count = len(full_content.split())

    return {
        "title": outline["title"],
        "slug": outline["slug"],
        "meta_title": outline["title"][:60],
        "meta_description": outline["meta_description"],
        "content": full_content,
        "word_count": actual_word_count,
        "schema_type": outline.get("schema_type", "Article"),
        "affiliate_programs_used": affiliate_suggestions,
        "faq": faq_items,
        "lsi_keywords": lsi_keywords,
        "target_keyword": keyword,
    }


def inject_affiliate_links(
    content: str,
    site: str,
    suggested_programs: list[str] | None = None,
    max_injections: int = 3,
) -> str:
    """
    Best-effort affiliate link injection using inline CTA syntax.
    In production, this should query AffiliateProgram from DB.
    """
    # Minimal hardcoded fallback map for generation-time injection
    # (Real injection happens at publish time against DB programs)
    FALLBACK_CTA = {
        "semrush": ("Try Semrush Free →", "https://semrush.com"),
        "jasper": ("Try Jasper AI →", "https://jasper.ai"),
        "hostinger": ("Get Hosting from $2.99/mo →", "https://hostinger.com"),
        "binance": ("Start Trading on Binance →", "https://binance.com"),
        "ledger": ("Secure Your Crypto with Ledger →", "https://ledger.com"),
    }

    injected = 0
    lines = content.split("\n")
    result_lines = []

    for line in lines:
        if line.startswith("#") or line.startswith("```") or "[" in line:
            result_lines.append(line)
            continue
        if injected >= max_injections:
            result_lines.append(line)
            continue

        for slug, (cta, url) in FALLBACK_CTA.items():
            if slug.lower() in line.lower() and len(line) > 40:
                line += f"\n\n> **[{cta}]({url})**\n"
                injected += 1
                break

        result_lines.append(line)

    return "\n".join(result_lines)


def generate_keyword_batch(site: str) -> list[dict[str, Any]]:
    """Generate 100+ keywords for a site using templates."""
    keywords = []
    templates = KEYWORD_TEMPLATES.get(site, {})

    if site == "site_a":
        tools = SITE_A_TOOLS
        categories = SITE_A_CATEGORIES

        for tool in tools:
            for tpl in templates.get("review", []):
                keywords.append({
                    "keyword": tpl.format(tool=tool),
                    "content_type": "review",
                    "priority": 7,
                })
            for tpl in templates.get("howto", []):
                keywords.append({
                    "keyword": tpl.format(tool=tool),
                    "content_type": "how_to",
                    "priority": 6,
                })

        # Comparison keywords (tool vs tool)
        for i, tool_a in enumerate(tools[:8]):
            for tool_b in tools[i + 1 : i + 4]:
                keywords.append({
                    "keyword": f"{tool_a} vs {tool_b}",
                    "content_type": "comparison",
                    "priority": 9,
                })

        for category in categories:
            for tpl in templates.get("best", []):
                keywords.append({
                    "keyword": tpl.format(category=category),
                    "content_type": "listicle",
                    "priority": 8,
                })

    elif site == "site_b":
        products = SITE_B_PRODUCTS
        actions = SITE_B_ACTIONS
        categories = SITE_B_CATEGORIES

        for product in products:
            for tpl in templates.get("review", []):
                keywords.append({
                    "keyword": tpl.format(product=product),
                    "content_type": "review",
                    "priority": 7,
                    "language": "th",
                })
            for action in actions:
                for tpl in templates.get("howto", []):
                    keywords.append({
                        "keyword": tpl.format(product=product, action=action),
                        "content_type": "how_to",
                        "priority": 6,
                        "language": "th",
                    })

        for category in categories:
            for tpl in templates.get("best", []):
                keywords.append({
                    "keyword": tpl.format(category=category),
                    "content_type": "listicle",
                    "priority": 8,
                    "language": "th",
                })

    # Deduplicate
    seen = set()
    unique = []
    for kw in keywords:
        k = kw["keyword"].lower()
        if k not in seen:
            seen.add(k)
            unique.append({
                **kw,
                "site": site,
                "language": kw.get("language", "en"),
            })
    return unique


def compute_content_hash(content: str) -> str:
    """SHA256 hash for deduplication detection."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
