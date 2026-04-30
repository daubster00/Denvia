"""결제 통합 패키지 — PG_PROVIDER 환경변수로 활성 어댑터 반환."""

from api.src.integrations.payment.port import PGProvider


def get_pg_provider() -> PGProvider:
    """settings.pg_provider에 따라 적절한 어댑터를 반환한다. 기본값: toss."""
    from api.src.settings import settings

    provider = settings.pg_provider
    if provider == "toss":
        from api.src.integrations.payment.adapters.toss import TossAdapter
        return TossAdapter(secret_key=settings.toss_secret_key)
    from api.src.integrations.payment.adapters.nicepay import NicepayAdapter
    return NicepayAdapter()
