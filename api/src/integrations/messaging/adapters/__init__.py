"""어댑터 팩토리 — MESSAGING_PROVIDER 환경변수로 구현체를 런타임 선택한다."""

from api.src.integrations.messaging.port import MessagingProvider


def get_adapter() -> MessagingProvider:
    """설정된 MESSAGING_PROVIDER에 맞는 어댑터 인스턴스를 반환한다."""
    from api.src.settings import settings

    provider = settings.messaging_provider.lower()

    if provider == "stub":
        from api.src.integrations.messaging.adapters.stub import StubMessagingAdapter
        return StubMessagingAdapter()

    if provider == "aligo":
        from api.src.integrations.messaging.adapters.aligo import AligoMessagingAdapter
        return AligoMessagingAdapter()

    if provider == "nhn_cloud":
        from api.src.integrations.messaging.adapters.nhn_cloud import NHNCloudMessagingAdapter
        return NHNCloudMessagingAdapter()

    raise ValueError(
        f"지원하지 않는 MESSAGING_PROVIDER: '{provider}'. "
        "유효한 값: 'stub', 'aligo', 'nhn_cloud'"
    )
