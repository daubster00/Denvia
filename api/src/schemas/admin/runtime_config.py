"""서비스 전체 런타임 설정 스키마 — Story 7.3/7.4 부분.

컨텐츠 관리 페이지에서 어드민이 직접 편집하는 4개 토글:
- show_subscribe_button: 구독 버튼 전역 노출 토글 (A-303)
- free_daily_quota: 무료 사용자 1일 질문 한도 (FR23)
- free_delay_enabled: 답변 의도적 지연 ON/OFF (A-305)
- free_delay_seconds: 무료 지연 초 (Story 6.3 정수 호환)

추가:
- ChatModelConfig*: 관리자 설정 페이지에서 RAG 본 체인 채팅 모델 선택.
"""

from pydantic import BaseModel, Field


class RuntimeConfigResponse(BaseModel):
    show_subscribe_button: bool
    free_daily_quota: int
    free_delay_enabled: bool
    free_delay_seconds: int
    free_delay_notice_text: str
    # Pro 구독자가 한 달 동안 사용할 수 있는 질문 횟수 상한 (KST 월초 기준 리셋).
    pro_monthly_quota: int


class RuntimeConfigUpdateRequest(BaseModel):
    show_subscribe_button: bool
    free_daily_quota: int = Field(ge=0, le=9999)
    free_delay_enabled: bool
    free_delay_seconds: int = Field(ge=0)
    free_delay_notice_text: str = Field(max_length=200)
    pro_monthly_quota: int = Field(ge=0, le=99999)


class ChatModelConfigResponse(BaseModel):
    """현재 선택된 채팅 모델 + 허용 모델 목록(드롭다운 옵션 제공)."""

    chat_model: str
    allowed_models: list[str]
    default_model: str


class ChatModelConfigUpdateRequest(BaseModel):
    chat_model: str = Field(min_length=1, max_length=64)


class AnomalyThrottleConfigResponse(BaseModel):
    """이상 질문 패턴 throttle 설정 — 관리자 페이지 표시·편집 형태.

    탐지 규칙: 답변 출력 완료 시각 기준 3초 이내 후속 질문 연속 3회.
    적용: 해당 사용자 ``users.anomaly_throttled_at`` 채워 다음 질의부터 무료/유료별
    설정된 초만큼 답변 시작 지연.
    """

    enabled: bool
    free_delay_seconds: float
    pro_delay_seconds: float


class AnomalyThrottleConfigUpdateRequest(BaseModel):
    enabled: bool
    free_delay_seconds: float = Field(ge=0, le=999.9)
    pro_delay_seconds: float = Field(ge=0, le=999.9)


class LoginBruteThresholdConfigResponse(BaseModel):
    """로그인 실패 이상탐지 기준 횟수 — 관리자 편집 형태.

    의미: 동일 이메일로 비밀번호가 ``threshold`` 회 이상 연속 실패하면
    1) anomaly_events 에 stage=1 이벤트 INSERT, 2) 해당 이메일을 10분간 잠금.
    bounds 와 default 도 함께 노출해 프론트 폼이 동적으로 안내 가능.
    """

    threshold: int
    default_threshold: int
    min_threshold: int
    max_threshold: int


class LoginBruteThresholdConfigUpdateRequest(BaseModel):
    # 1 = 첫 실패에 바로 락(엄격), 20 = 사실상 비활성에 가까운 느슨한 운영.
    threshold: int = Field(ge=1, le=20)


class AnomalyThresholdsItem(BaseModel):
    """관리자 페이지 prefill 용 — 현재값 + 기본값 + bounds 묶음.

    float 로 통일해 시각(소수 초) 항목과 횟수(정수) 항목을 같은 폼이 다룰 수 있게 한다.
    """

    current: float
    default: float
    min: float
    max: float


class AnomalyThresholdsConfigResponse(BaseModel):
    """이상탐지 임계값 11개 묶음 응답.

    의미와 적용 동작:
    - login_brute_threshold: 동일 이메일 N회 연속 실패 시 anomaly + lockout.
    - login_lockout_seconds: 위 잠금 지속 시간(초).
    - concurrent_ip_threshold / concurrent_ip_window_seconds:
      같은 IP에서 N명 이상이 윈도우 안에 로그인하면 각 사용자 anomaly INSERT.
    - repeated_question_threshold: 같은 질문 N회 연속 시 자동 throttle.
    - rapid_followup_window_seconds / rapid_followup_threshold:
      답변 완료 N초 안에 새 질문이 N회 연속이면 자동 throttle.
    - sms_max_retries: 시간당 OTP 발송 허용 횟수 (초과 시 429).
    - sms_abuse_threshold: 1시간 누적 OTP 시도 N회 도달 시 24시간 차단 + anomaly.
    - sms_max_wrong: OTP 검증 오답 허용 횟수.
    - recovery_abuse_threshold: 1시간 비밀번호/아이디 찾기 시도 N회 도달 시 anomaly.
    """

    login_brute_threshold: AnomalyThresholdsItem
    login_lockout_seconds: AnomalyThresholdsItem
    concurrent_ip_threshold: AnomalyThresholdsItem
    concurrent_ip_window_seconds: AnomalyThresholdsItem
    repeated_question_threshold: AnomalyThresholdsItem
    rapid_followup_window_seconds: AnomalyThresholdsItem
    rapid_followup_threshold: AnomalyThresholdsItem
    sms_max_retries: AnomalyThresholdsItem
    sms_abuse_threshold: AnomalyThresholdsItem
    sms_max_wrong: AnomalyThresholdsItem
    recovery_abuse_threshold: AnomalyThresholdsItem


class AnomalyThresholdsConfigUpdateRequest(BaseModel):
    """일괄 저장 요청 — 서버에서 추가 clamp."""

    login_brute_threshold: int = Field(ge=1, le=20)
    login_lockout_seconds: int = Field(ge=60, le=86400)
    concurrent_ip_threshold: int = Field(ge=2, le=50)
    concurrent_ip_window_seconds: int = Field(ge=60, le=3600)
    repeated_question_threshold: int = Field(ge=2, le=50)
    rapid_followup_window_seconds: float = Field(ge=0.5, le=60.0)
    rapid_followup_threshold: int = Field(ge=2, le=50)
    sms_max_retries: int = Field(ge=1, le=20)
    sms_abuse_threshold: int = Field(ge=2, le=100)
    sms_max_wrong: int = Field(ge=1, le=20)
    recovery_abuse_threshold: int = Field(ge=2, le=50)


class ForexConfigResponse(BaseModel):
    """USD→KRW 환율 + 자동 갱신 메타 — 관리자 UI 표시 전용 (read-only).

    자동 갱신 정책: Celery beat 가 매일 09:00 KST 한국수출입은행 API 호출.
    실패·미설정 시 ``DEFAULT_USD_TO_KRW``(1400) 폴백.
    """

    rate: int
    default_rate: int
    updated_at: str | None  # ISO8601 UTC, 한 번도 자동 갱신 안 됐으면 None
    search_date: str | None  # YYYY-MM-DD, API 가 데이터 반환한 영업일
    source: str  # "auto" | "fallback" — auto_renew 우선 정책 명시


# ─────────────────────────────────────────────────────────────────────────────
# 토스 PG 키 관리 — /admin/settings/payment 페이지에서 4개 키 + 모드 편집.
# ─────────────────────────────────────────────────────────────────────────────


class TossPgKeyView(BaseModel):
    """단일 키 표시 — 원본 노출 금지, 마스킹된 문자열 + 존재 여부."""

    masked: str
    has_value: bool


class TossPgConfigResponse(BaseModel):
    """관리자 GET 응답 — 모드 + 4개 키 마스킹 묶음.

    클라이언트 키 2개는 프론트 결제창에서 어차피 노출되는 값이지만, 관리자 UI
    에서는 일관되게 마스킹해서 보여주고 "수정" 클릭 시에만 빈 입력창을 띄운다.
    secret 키 2개는 절대로 평문으로 응답에 실리지 않는다.
    """

    mode: str  # "test" | "live"
    test_client: TossPgKeyView
    test_secret: TossPgKeyView
    live_client: TossPgKeyView
    live_secret: TossPgKeyView


class TossPgConfigUpdateRequest(BaseModel):
    """부분 업데이트 — None 또는 빈 문자열인 필드는 그대로 둔다.

    예) 모드만 토글: ``{"mode": "live"}``
    예) live secret 만 교체: ``{"live_secret_key": "live_sk_..."}``
    """

    mode: str | None = Field(default=None, description="test | live")
    test_client_key: str | None = Field(default=None, max_length=512)
    test_secret_key: str | None = Field(default=None, max_length=512)
    live_client_key: str | None = Field(default=None, max_length=512)
    live_secret_key: str | None = Field(default=None, max_length=512)


class TossPgClientConfigResponse(BaseModel):
    """공개 엔드포인트 응답 — 활성 모드 + 그 모드의 client_key.

    프론트 BillingKeyForm 이 결제창 초기화 직전에 호출한다. 관리자가 키를
    바꾸자마자 다음 결제 시도부터 새 키가 적용된다(빌드 재배포 불필요).
    client_key 가 비어있으면 결제창은 사용 불가 안내로 폴백.
    """

    mode: str
    client_key: str  # 빈 문자열이면 미설정
