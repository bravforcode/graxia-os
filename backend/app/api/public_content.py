from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.content_engine import ContentArticle

router = APIRouter(prefix="/public/content", tags=["public-content"])


class PublicContentArticle(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    title: str
    title_th: str | None = None
    language: str
    content_type: str
    meta_title: str | None = None
    meta_description: str | None = None
    body: str
    hero_image_url: str | None = None
    published_url: str | None = None
    published_at: datetime | None = None


@router.get("/articles/{slug}", response_model=PublicContentArticle)
async def get_published_article(
    slug: str,
    language: str | None = Query(None, pattern="^(en|th)$"),
    db: AsyncSession = Depends(get_db),
) -> PublicContentArticle:
    filters = [
        ContentArticle.slug == slug,
        ContentArticle.status == "published",
    ]
    if language:
        filters.append(ContentArticle.language == language)
    article = (
        await db.execute(
            select(ContentArticle)
            .where(*filters)
            .order_by(ContentArticle.published_at.desc(), ContentArticle.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=404, detail="Published article not found")
    return PublicContentArticle.model_validate(article)
