"""Denvia API 설정 — pydantic-settings 기반 환경변수 로딩."""

from decimal import Decimal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Redis DB 번호 고정 용도 상수
REDIS_DB_CELERY = 0      # Celery broker / result
REDIS_DB_OTP = 1         # OTP (5분 TTL)
REDIS_DB_RATE_LIMIT = 2  # Rate Limit
REDIS_DB_RUNTIME_CONFIG = 3  # RuntimeConfig (관리자 편집값 캐시)
REDIS_DB_QUOTA = 4       # Quota


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 환경 — development | staging | production (쿠키 secure 등 분기용)
    environment: str = "development"

    # 데이터베이스
    database_url: str = "postgresql+psycopg://denvia:password@postgres:5432/denvia"
    database_sync_url: str = "postgresql+psycopg://denvia:password@postgres:5432/denvia"

    # Redis
    redis_url: str = "redis://redis:6379"

    # JWT
    denvia_jwt_secret: str = "change_me_in_production_minimum_32_chars"
    denvia_jwt_algorithm: str = "HS256"

    # 관리자 초기 계정
    denvia_admin_email: str = "admin@denvia.ai.kr"
    denvia_admin_initial_password: str = "change_me_in_production"

    # 예산 통제 (Story 5.2)
    denvia_initial_monthly_budget_usd: Decimal = Decimal("100.00")

    # Observability
    sentry_dsn_api: str = ""
    sentry_environment: str = "development"

    # 결제 PG (Story 3.1)
    pg_provider: str = "toss"                         # toss | nicepay (PG_PROVIDER)
    pro_monthly_price_krw: int = 9900                 # Pro 플랜 월 가격 (원)

    # 토스페이먼츠 (Story 3.2)
    toss_secret_key: str = ""                         # TOSS_SECRET_KEY — 서버 전용, 절대 프론트 노출 금지

    # 메시징 어댑터 (Story 4.1)
    messaging_provider: str = "stub"           # stub | aligo | nhn_cloud
    alimtalk_template_map_json: str = "{}"     # {"billing.first_charge_success": "TX_001", ...}

    # 알리고 (Aligo) — 알림톡·SMS 공급자 (AR35 해제, 2026-05-07)
    aligo_api_key: str = ""                    # ALIGO_API_KEY — 알리고 마이페이지 발급
    aligo_user_id: str = ""                    # ALIGO_USER_ID — 알리고 가입 ID
    aligo_sender: str = ""                     # ALIGO_SENDER — 사전 인증된 발신번호 (예: "01012345678")
    aligo_sender_key: str = ""                 # ALIGO_SENDER_KEY — 알림톡 송신프로필키 (카카오 비즈니스 채널 인증 후 발급)
    aligo_test_mode: bool = True               # ALIGO_TEST_MODE=false 로 프로덕션 실발송
    aligo_sms_base_url: str = "https://apis.aligo.in"
    aligo_alimtalk_base_url: str = "https://kakaoapi.aligo.in"

    # WebOTP API — Android Chrome SMS 자동 입력용 도메인 바운드 (예: "denvia.com"). 비우면 마커 라인 미부착.
    webotp_bound_origin: str = ""

    # 한국수출입은행 환율 API — USD→KRW 매일 09:00 KST 자동 갱신용 (Story 5.5 후속)
    # 미설정 시 forex_tasks 가 no-op 처리 → Redis 기존값 유지, 폴백 1,400.
    koreaexim_api_key: str = ""
    koreaexim_base_url: str = "https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON"

    # RAG 통합 (Story 2.1)
    faiss_current_path: str = "data/faiss/current"
    faiss_index_a_path: str = "data/faiss/index_a"
    faiss_index_b_path: str = "data/faiss/index_b"

    # OAuth 3종 (Story 1.6) — 개발자 개인 키, 인수 시 교체
    kakao_client_id: str = ""
    kakao_client_secret: str = ""
    kakao_redirect_uri: str = "http://localhost:8000/api/v1/auth/oauth/kakao/callback"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/oauth/google/callback"
    naver_client_id: str = ""
    naver_client_secret: str = ""
    naver_redirect_uri: str = "http://localhost:8000/api/v1/auth/oauth/naver/callback"
    oauth_web_origin: str = "http://localhost:3000"


settings = Settings()
