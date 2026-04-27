"""Me 관련 Pydantic 스키마 — Story 2.3."""

from pydantic import BaseModel


class QuotaResponse(BaseModel):
    subscription_status: str
    daily_limit: int
    used_today: int
    remaining: int
    reset_at: str
    show_upgrade_prompt: bool
    show_subscribe_button: bool
    delay_seconds: int
