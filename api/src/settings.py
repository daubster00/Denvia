"""Denvia API 설정 — pydantic-settings 기반 환경변수 로딩."""

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
    denvia_admin_email: str = "admin@denvia.local"
    denvia_admin_initial_password: str = "change_me_in_production"

    # Observability
    sentry_dsn_api: str = ""
    sentry_environment: str = "development"

    # 메시징 어댑터 (Story 4.1)
    messaging_provider: str = "stub"           # stub | aligo | nhn_cloud
    alimtalk_template_map_json: str = "{}"     # {"billing.first_charge_success": "KA01234", ...}

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
