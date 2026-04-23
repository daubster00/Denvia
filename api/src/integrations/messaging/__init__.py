"""메시징 통합 패키지 — 알림톡·SMS 어댑터 및 NotificationService 노출."""

from api.src.integrations.messaging.notification_service import (
    NotificationService,
    get_notification_service,
)
from api.src.integrations.messaging.port import AlimtalkResult, MessagingProvider
from api.src.integrations.messaging.templates import (
    TEMPLATE_CATALOG,
    TemplateCategory,
    TemplateDefinition,
)

__all__ = [
    "MessagingProvider",
    "AlimtalkResult",
    "TemplateCategory",
    "TemplateDefinition",
    "TEMPLATE_CATALOG",
    "NotificationService",
    "get_notification_service",
]
