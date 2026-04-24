# 코딩 컨벤션

> **최종 수정일:** 2026-04-24
> **작성자:** Hyung woo
> **승인자:** (인수자 검토 시 기입)
> **버전:** v1.0
> **관련 FR/Story:** NFR-M1·NFR-S7 / Story 9.5a

> **주의:** 본 문서는 rules-as-code를 지향하나 Python/TS 린터 자동 검증은 일부만 커버(ruff·ESLint 기본 규칙). 나머지는 코드 리뷰 수동 확인이 필요하다.

---

## §1. 케이스 규칙

### snake_case 전파 원칙

DB(PostgreSQL 16 snake_case) → Python(snake_case) → API JSON(snake_case) → TS(snake_case) 전파를 유지한다.

**자동 변환 레이어 금지**: Pydantic `alias_generator`·프런트 camelCase 컨버터를 도입하지 않는다.

근거: `api/src/schemas/auth.py:1` 파일 최상단 주석 — `"""인증 관련 Pydantic 스키마 — snake_case, 래퍼 금지 (architecture.md §703)."""`

**예외**: React 컴포넌트명·hooks 훅명은 `camelCase`/`PascalCase` TypeScript 관례를 유지한다.

| 계층 | 규칙 | 예시 |
|---|---|---|
| PostgreSQL 컬럼 | snake_case | `created_at`, `phone_verified` |
| Python 변수·함수·스키마 필드 | snake_case | `user_id`, `get_current_user` |
| API JSON 키 | snake_case | `{"user_id": 1, "created_at": "..."}` |
| TypeScript 변수·인터페이스 필드 | snake_case | `const user_id = ...` |
| React 컴포넌트 | PascalCase | `LoginPopup`, `PhoneVerifyClient` |
| React hooks | camelCase | `useAuthStore`, `useSession` |

---

## §2. 폴더 구조

### 프런트엔드: by-feature

`web/src/features/` 하위에 기능 단위 폴더를 구성한다.

현 실재 구조:
```
web/src/
├── app/          # Next.js App Router 페이지
├── features/
│   ├── auth/     # ✅ 실재 (LoginPopup, OAuthErrorBanner, SocialLoginTab 등)
│   └── qa/       # ⏳ Story 2.1에서 생성 예정
└── lib/          # 공용 유틸리티
```

### 백엔드: by-layer

`api/src/` 하위에 계층 단위 폴더를 구성한다.

현 실재 구조:
```
api/src/
├── routers/        # ✅ auth.py, health.py, me.py
├── services/       # ✅ auth_service.py
├── models/         # ✅ oauth_identity.py 등
├── schemas/        # ✅ auth.py
├── integrations/   # ✅ auth_providers/, messaging/
├── workers/        # ✅ celery_app.py, notification_tasks.py
├── utils/          # ✅ argon2.py, jwt.py, korean_time.py, mask.py
├── middleware/     # ✅ audit.py, rate_limit.py, trace.py
└── deps/           # ✅ rate_limit.py
```

### 금지 역방향 의존 4가지

`architecture.md L1153-1156, L1171-1175` 기준:

1. `models/` → `routers/` 역방향 참조 금지
2. `services/` → `routers/` 역방향 참조 금지
3. `routers/` → `models/` 직접 접근 금지 (services 경유 필수)
4. `integrations/` 내부 구현을 `routers/`에서 직접 import 금지 (포트-어댑터 원칙)

---

## §3. 라우터·서비스·모델·스키마 의존 방향

의존 가능·금지 조합 (`architecture.md L1160-1168`):

| 계층 | 의존 가능 | 의존 금지 |
|---|---|---|
| `routers/` | `services/`, `schemas/`, `deps/`, `middleware/` | `models/` 직접 접근, `integrations/` 직통 import |
| `services/` | `models/`, `schemas/`, `integrations/`, `utils/` | `routers/` |
| `models/` | (ORM 정의만, 외부 의존 최소화) | `routers/`, `services/`, `schemas/` |
| `schemas/` | 표준 라이브러리, Pydantic | `models/`, `services/` |
| `integrations/` | 외부 SDK, `utils/` | `routers/`, `services/` |

**위반 탐지 방법**: 코드 리뷰에서 import 경로 수동 확인. 향후 ruff 커스텀 룰 도입 검토.

---

## §4. 한글 주석 규약

NFR-M1(`prd.md L691, L461`) 기준: 모든 주석·docstring을 한글로 작성하고, 기술 용어는 영문 원어를 병기한다.

### 의무 주석 3종

1. **함수·클래스 docstring** — 역할 1~3행
2. **비자명 분기 근거** — 왜 이 조건인지
3. **설정값 의미** — 환경변수·상수

### Good 예시 (실재 코드)

```python
# good ① — api/scripts/seed_admin.py:1
"""관리자 초기 계정 삽입 스크립트 — 멱등 보장 (이미 존재하면 skip)."""
```

```python
# good ② — api/src/middleware/trace.py:1-3
"""X-Trace-Id 미들웨어 — 요청·응답 양방향으로 trace_id를 주입하고
structlog contextvars에 바인딩하여 로그 호출 시 자동 첨부한다.
"""
```

```python
# good ③ — api/src/main.py:20-26
# PII 스크러빙 프로세서 — 이메일·휴대폰·비밀번호를 로그에서 마스킹
def _scrub_pii(event, hint):
    """Sentry 이벤트에서 PII 필드를 제거한다."""
    for key in ("email", "phone", "password", "password_hash"):
        if key in event.get("extra", {}):
            event["extra"][key] = "[REDACTED]"
    return event
```

### Bad 예시 (가공)

```python
# bad ① — 자명한 주석 (제거 대상)
def add_one(x):
    return x + 1  # x에 1을 더한다
```

```python
# bad ② — 구체 Story 번호·이유 없는 TODO
# TODO: 나중에 고치기
```

---

## §5. 실 코드 Good/Bad 샘플 블록

### Good — `api/src/middleware/trace.py` 전문 (27줄)

```python
"""X-Trace-Id 미들웨어 — 요청·응답 양방향으로 trace_id를 주입하고
structlog contextvars에 바인딩하여 로그 호출 시 자동 첨부한다.
"""

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from ulid import ULID


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get("X-Trace-Id") or str(ULID())
        request.state.trace_id = trace_id

        # structlog contextvars에 바인딩 — 이후 모든 logger.info 호출에 trace_id 자동 첨부
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)

        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()

        response.headers["X-Trace-Id"] = trace_id
        return response
```

### Bad — 에러 처리 없는 API 호출 (가공 예시)

```javascript
// bad — 에러 처리 없음, camelCase 자동 변환 의존
async function fetchUser(userId) {
  const res = await fetch(`/api/users/${userId}`)
  const data = await res.json()
  // response가 camelCase라고 가정, snake_case SSOT 위반
  return data.userId  // 실제로는 data.user_id
}
```

---

## §6. PR 템플릿 체크박스 해석

**SSOT**: 본 섹션과 `.github/PULL_REQUEST_TEMPLATE.md`(Story 1.1 기존, 본 스토리 Task 7에서 9 체크박스로 병합 갱신)는 동일 문면을 유지한다. 둘 중 하나를 변경하면 나머지도 동기 갱신해야 한다.

| 번호 | 항목 | 판단 기준 |
|---|---|---|
| ① | 한글 주석 완료 (NFR-M1) | 함수 docstring·비자명 분기·설정값 주석이 모두 한글로 작성되어 있는가 |
| ② | 감사 로그 대상 확인 (NFR-S7) | 8종 감사 액션 해당 시 `middleware/audit.py` 기록이 포함되어 있는가 |
| ③ | 외부 연동 어댑터 경유 | `integrations/<provider>/` 직통 import 없이 포트-어댑터 원칙을 준수하는가 |
| ④ | Pydantic 스키마 변경 시 zod 동기화 완료 | snake_case SSOT 양방향(API 스키마 ↔ 프런트 zod) 동기화가 완료되었는가 |
| ⑤ | PII 로그 출력 없음 | `_scrub_pii` 대상 4필드(`email`·`phone`·`password`·`password_hash`)를 직접 logger로 출력하지 않는가 |
| ⑥ | `vendor/rag/` 또는 `자료/RAG 코드/` 경로 변경 없음 | RAG 경로를 변경했다면 아래 ⑨ 섹션을 필수 작성했는가 |
| ⑦ | SSOT 편차 유발 여부 | PRD 기준과 다른 결정이 필요할 경우 새 ADR을 추가했는가 (`docs/adr/0001-ssot-deviations.md` 참조) |
| ⑧ | 레이트 리밋 영향 여부 | 신규 엔드포인트 추가 시 `deps/rate_limit.py`에 반영했는가 |
| ⑨ | RAG 수정 시 의도 보존 3문항 (ADR-0002 §결정) | RAG 미수정 PR은 N/A. 수정 PR은 아래 3문항 모두 Yes여야 함. |

**⑨ RAG 의도 보존 3문항** (ADR-0002 §결정 — 세부 기준):
- 동일 입력 → 동일 출력 유지 (텍스트·문서 메타·토큰량 ± 허용 오차)
- 동의어 정규화·장애인가산 매칭 결과가 기존과 동일 (`test_rag_contract.py` 회귀 테스트 통과)
- 모델·retriever 파라미터 기본값 유지 (`text-embedding-3-large`·`o4-mini`·`k=5`)

---

## §7. 관측·로깅 규약

### trace_id 전파

`api/src/middleware/trace.py:12-27` 실재 코드 기준:
- ULID 생성: `str(ULID())` — 요청 헤더 `X-Trace-Id` 부재 시 신규 생성
- structlog contextvars 바인딩: `bind_contextvars(trace_id=trace_id)`
- 응답 헤더: `X-Trace-Id` 양방향 전파

### Sentry PII 스크러빙

`api/src/main.py:20-26` `_scrub_pii`:
- 대상 4필드: `email`, `phone`, `password`, `password_hash`
- 처리 방식: Sentry `before_send` 훅에서 `event["extra"][key] = "[REDACTED]"`

### 사용자 노출 이메일 부분 마스킹

`api/src/utils/mask.py` `mask_email` 함수(16줄 단일 함수 유틸):
- 로컬파트 2자 이상: `a****@domain`
- 로컬파트 1자 이하: `*****@domain`
- 목적: 로그·UI 노출 시 이메일 일부만 표시

### 이벤트명 규칙

`architecture.md L1333` 기준: `<domain>.<verb>_<subject>` 패턴.

| 구분 | 예시 |
|---|---|
| good ① | `auth.login_success` |
| good ② | `payment.webhook_received` |
| good ③ | `rag.query_completed` |
| bad ① | `loginSuccess` (camelCase, 도메인 구분 없음) |
| bad ② | `user_login` (동사 뒤에 목적어 순서 반대) |
| bad ③ | `event` (너무 포괄적) |
