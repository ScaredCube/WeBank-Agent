from fastapi import APIRouter

from app.agent.llm import get_llm_info
from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "llm": get_llm_info(),
    }
