"""결제 통합 패키지 — PG_PROVIDER 환경변수로 활성 어댑터 반환.

토스 secret_key 는 Redis(runtime:pg:*) 가 SSOT. 미설정 시 ``settings.toss_secret_key``
(env) 로 폴백. 관리자 페이지에서 키를 저장하면 다음 결제 호출부터 즉시 반영된다.
"""

from api.src.integrations.payment.port import PGProvider


def get_pg_provider() -> PGProvider:
    """settings.pg_provider 에 따라 적절한 어댑터를 반환한다. 기본값: toss.

    토스 모드(test|live) + 활성 secret_key 는 Redis 에서 읽고, 없으면 env 폴백.
    """
    from api.src.settings import settings

    provider = settings.pg_provider
    if provider == "toss":
        from api.src.integrations.payment.adapters.toss import TossAdapter
        from api.src.services.pg_config_service import resolve_active_toss_secret_sync

        return TossAdapter(secret_key=resolve_active_toss_secret_sync())
    from api.src.integrations.payment.adapters.nicepay import NicepayAdapter
    return NicepayAdapter()
