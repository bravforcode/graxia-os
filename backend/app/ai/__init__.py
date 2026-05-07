"""
Graxia AI Module
Multi-model AI integration with Obsidian vault and agent network
"""

from fastapi import APIRouter

router = APIRouter(prefix="/ai", tags=["AI"])

from . import router as ai_router
