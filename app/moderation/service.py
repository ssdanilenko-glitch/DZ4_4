import hashlib
import re
from pathlib import Path
from typing import Optional

import structlog
import yaml
from pydantic import BaseModel

from app.core.config import get_settings

logger = structlog.get_logger()


class ModerationResult(BaseModel):
    allowed: bool
    categories: list[str] = []
    reasons: list[str] = []
    blocked_by: str = ""


class ModerationService:
    def __init__(self, openai_client=None):
        self.settings = get_settings()
        self.openai_client = openai_client
        self._patterns = self._load_keywords()
        self._enabled = getattr(self.settings, "MODERATION_ENABLED", True)
        self._use_openai = getattr(self.settings, "MODERATION_USE_OPENAI", False)

    def _load_keywords(self) -> list[dict]:
        path = Path(__file__).parent / "keywords.yaml"
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("patterns", [])

    async def _check_keywords(self, text: str) -> Optional[ModerationResult]:
        for item in self._patterns:
            if re.search(item["pattern"], text):
                return ModerationResult(
                    allowed=False,
                    categories=[item["category"]],
                    reasons=[item["reason"]],
                    blocked_by="keywords",
                )
        return None

    async def _check_openai(self, text: str) -> Optional[ModerationResult]:
        if not self._use_openai or not self.openai_client:
            return None
        try:
            resp = await self.openai_client.moderations.create(
                model="omni-moderation-latest",
                input=text,
            )
            result = resp.results[0]
            if not result.flagged:
                return None

            # кастомные пороги: блокируем, если score > threshold
            threshold = getattr(self.settings, "MODERATION_THRESHOLD", 0.7)
            blocked_categories = []
            for cat, score in result.category_scores.model_dump().items():
                if score > threshold:
                    blocked_categories.append(cat)

            if not blocked_categories:
                return None

            return ModerationResult(
                allowed=False,
                categories=blocked_categories,
                reasons=["openai moderation score above threshold"],
                blocked_by="openai",
            )
        except Exception as exc:
            logger.warning("moderation_openai_failed", error=str(exc))
            return None  # fail-open

    async def check_input(self, content: str) -> ModerationResult:
        if not self._enabled:
            return ModerationResult(allowed=True)

        result = await self._check_keywords(content)
        if result and not result.allowed:
            self._log_incident(content, result)
            return result

        result = await self._check_openai(content)
        if result and not result.allowed:
            self._log_incident(content, result)
            return result

        return ModerationResult(allowed=True)

    async def check_output(self, content: str) -> ModerationResult:
        # для output можно пропустить keyword-слой или использовать отдельный список
        result = await self._check_openai(content)
        if result and not result.allowed:
            self._log_incident(content, result)
            return result
        return ModerationResult(allowed=True)

    def _log_incident(self, text: str, result: ModerationResult):
        logger.warning(
            "moderation_blocked",
            text_hash=hashlib.sha256(text.encode()).hexdigest()[:16],
            text_masked=self._mask_pii(text),
            categories=result.categories,
            blocked_by=result.blocked_by,
        )

    @staticmethod
    def _mask_pii(text: str) -> str:
        # упрощённая маскировка email/телефона; заменить на функцию из МЗБ6 при наличии
        text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[EMAIL]", text)
        text = re.sub(r"\+?\d[\d\s\-()]{7,}\d", "[PHONE]", text)
        return text[:200]