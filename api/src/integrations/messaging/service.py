"""메시징 서비스 호환 레이어 — IMessagingService는 port.py의 MessagingProvider로 위임된다.

Story 1.1에서 ABC로 정의된 IMessagingService를 Story 4.1의 MessagingProvider Protocol 기반으로
마이그레이션. Story 1.3 구현 시에는 MessagingProvider(port.py)를 직접 사용할 것.
"""

from api.src.integrations.messaging.port import AlimtalkResult, MessagingProvider

# Story 1.3 이후 코드에서는 port.py의 MessagingProvider를 직접 import하여 사용하라.
# 아래 별칭은 하위 호환용이며 새 코드에서 사용 금지.
IMessagingProvider = MessagingProvider
IMessagingService = MessagingProvider  # AC-1 호환 — Story 1.1 ABC 교체 경로 유지
