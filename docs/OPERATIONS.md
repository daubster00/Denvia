# OPERATIONS — Denvia 운영 SOP(Standard Operating Procedure)

> **최종 수정일:** 2026-04-24
> **작성자:** Hyung woo
> **승인자:** (인수자 검토 시 기입)
> **버전:** v1.0
> **관련 FR/Story:** FR10·FR11·FR28·FR55·FR56·FR57 / Story 9.4

> **인덱스 안내:** 본 `docs/` 디렉터리의 통합 인덱스(`docs/README.md`)는 **Story 9.5 — 기술 레퍼런스 문서화** 범위이므로 본 스토리에서 생성하지 않는다. 본 문서가 일시적으로 운영 문서의 진입점 역할을 한다.

---

## 0. 본 문서의 사용 방법

본 문서는 Denvia 서비스의 일상 운영을 인수자가 **개발사 의존 없이 수행**하기 위한 표준 작업 절차다.

- **일일·주간·월간 체크리스트**(§1·§2·§3): 정해진 주기로 반드시 수행.
- **재인덱싱 가이드**(§4): RAG(Retrieval-Augmented Generation) 지식베이스 갱신 시 사용.
- **kill-switch(비상 정지 스위치) 운용 SOP**(§5): 예산 통제·시스템 비상시 사용.
- **알림톡 템플릿·공급자 교체 절차**(§6): 메시징 시스템 운영 변경 시 사용.

각 섹션의 명령어·엔드포인트·파일 경로는 모두 실재 검증되었거나, 미구현 항목은 `(TBD — Story X.Y)` 표기로 명시한다(AC-10 규약).

---

## 1. 일일 체크리스트

매 영업일 아침 **5분** 내 완료한다.

### 1.1 관리자 대시보드 KPI 확인

- 접근: `/admin`
  - Story 5.1에서 관리자 셸·권한 가드·placeholder 대시보드가 구현되어 있다.
  - KPI 위젯과 세부 분석 페이지는 Story 5.2~5.5 범위이므로, 해당 스토리 완료 전에는 데이터베이스 직접 조회로 대체한다:
    ```sql
    -- 어제 일자 질의 수·토큰·예산 % 조회 (admin 로그인 후 SQL 클라이언트 사용)
    SELECT
      DATE(created_at) AS d,
      COUNT(*) AS qa_count,
      SUM(prompt_tokens + completion_tokens) AS total_tokens
    FROM qa_logs
    WHERE created_at >= NOW() - INTERVAL '24 hours'
    GROUP BY d;
    ```
  - 단, `qa_logs` 테이블은 Story 2.1·2.2에서 생성 예정(현재 미생성, **TBD**).
- 확인 항목:
  - 총 질의 수(전일 대비 ±30% 이상 변동 시 §RUNBOOK_INCIDENT 시나리오 ⑥ 참조 — 변동률은 아래 SQL로 계산)
    ```sql
    -- 전일 대비 질의 수 변동률 계산 (TBD: qa_logs는 Story 2.1)
    WITH daily AS (
      SELECT DATE(created_at) AS d, COUNT(*) AS cnt
      FROM qa_logs
      WHERE created_at >= NOW() - INTERVAL '2 days'
      GROUP BY DATE(created_at)
    )
    SELECT
      d, cnt,
      LAG(cnt) OVER (ORDER BY d) AS prev_cnt,
      ROUND(100.0 * (cnt - LAG(cnt) OVER (ORDER BY d)) / NULLIF(LAG(cnt) OVER (ORDER BY d), 0), 1) AS pct_change
    FROM daily ORDER BY d DESC;
    -- |pct_change| >= 30 이면 시나리오 ⑥ 진단 절차로 (anomaly_events 테이블 함께 확인)
    ```
  - 누적 토큰 사용량
  - 월 예산 사용률 % — 80% 도달 시 알림톡 자동 수신 확인 (알림톡 수신 실패 시 §1.2 fallback 절차)

### 1.2 알림톡 수신 로그 확인(관리자 휴대폰)

- 관리자 등록 휴대폰(DB `users.phone` — `admin_recipient.resolve_admin_target` 가 조회. `btmdesign@naver.com` 우선, `admin@denvia.ai.kr` 차순위. 환경변수 폴백 없음)으로 수신된 알림톡 확인.
- 정상 수신 카테고리:
  - `system.*` (예: `admin.budget_warning_80`) — 항상 수신
  - `billing.*` (예: `billing.retry_failed_*`) — 결제 실패 발생 시
- **신호:** `system.*` 알림톡이 24시간 이상 수신되지 않음 → 알림톡 어댑터 장애 의심 → §RUNBOOK_INCIDENT 시나리오 ② 진단 절차 수행.

#### 1.2.1 알림톡 미수신 시 SMS 폴백 작동 검증

알림톡 공급자 장애 시 자동으로 LMS SMS 폴백(Story 4.1 정책)이 발송된다. 80/95/100% 예산 경고도 동일 폴백 경로 적용.

- 수신 채널 확인 순서:
  1. 알림톡 (`channel='alimtalk'`) — 정상 경로
  2. LMS SMS (`channel='sms'`, `status='fallback_sent'`) — 알림톡 실패 시 자동
  3. 둘 다 실패 시 `notification_queue.status='failed'` 영구 기록 → §RUNBOOK_INCIDENT 시나리오 ② 수동 처리
- 검증 SQL (TBD: notification_queue는 Story 4.1 완료, `api/src/models/notification_queue.py` 실재):
  ```sql
  SELECT channel, status, COUNT(*) AS cnt
  FROM notification_queue
  WHERE recipient_phone = (SELECT phone FROM users WHERE role='admin' LIMIT 1)
    AND created_at >= NOW() - INTERVAL '24 hours'
  GROUP BY channel, status
  ORDER BY cnt DESC;
  ```

### 1.3 FAISS `current` symlink 정상 여부

- FAISS(Facebook AI Similarity Search) 인덱스는 `index_a` / `index_b` 이중화 구조이며 `current` symlink가 활성 인덱스를 가리킨다.
- 확인:
  ```bash
  # API 컨테이너 진입
  docker compose -f infra/docker-compose.yml exec api ls -la /workspace/rag/data/faiss/
  # 출력 예: current -> /workspace/rag/data/faiss/index_a
  ```
- **(TBD — Story 8.3)**: 현 시점 `rag/` 디렉터리 및 FAISS 자산이 미구축이므로 본 항목은 Story 8.3 완료 후 검증 가능. 그 이전에는 본 점검을 건너뛴다.

---

## 2. 주간 작업

매주 월요일 오전 **15분** 내 완료한다.

### 2.1 PostgreSQL 백업 검증

- 권장 스크립트: `infra/scripts/backup-postgres.sh` **(TBD — Story 9.5 또는 별도 인프라 정비 시 추가 예정)**
  - 현재 본 스크립트는 미작성. 임시 절차:
    ```bash
    # 1) 백업 — 호스트에서 직접 pg_dump (Docker 컨테이너 대상)
    # ⚠️ --clean --if-exists는 복원 시 DROP TABLE을 포함하므로 잘못된 DB에 복원하면 데이터 파괴
    #    복원 시 반드시 별도 빈 DB 또는 테스트 환경 사용 (운영 DB 절대 금지)
    docker compose -f infra/docker-compose.yml exec -T postgres \
      pg_dump -U denvia -d denvia --no-owner --clean --if-exists \
      > "backups/denvia-$(date +%Y%m%d).sql"

    # 2) 백업 무결성 검증 — 별도 빈 DB(`denvia_verify`)에 실제 복원 후 카운트 비교
    # 2a) 빈 검증 DB 준비
    docker compose -f infra/docker-compose.yml exec -T postgres \
      psql -U denvia -d postgres -c "DROP DATABASE IF EXISTS denvia_verify;"
    docker compose -f infra/docker-compose.yml exec -T postgres \
      psql -U denvia -d postgres -c "CREATE DATABASE denvia_verify OWNER denvia;"

    # 2b) 백업 파일 복원 (denvia_verify 대상)
    docker compose -f infra/docker-compose.yml exec -T postgres \
      psql -U denvia -d denvia_verify < "backups/denvia-$(date +%Y%m%d).sql"

    # 2c) 행수 비교 (운영 vs 검증 DB가 동일해야 정상)
    docker compose -f infra/docker-compose.yml exec -T postgres \
      psql -U denvia -d denvia -c "SELECT 'prod' AS db, count(*) FROM users;"
    docker compose -f infra/docker-compose.yml exec -T postgres \
      psql -U denvia -d denvia_verify -c "SELECT 'verify' AS db, count(*) FROM users;"

    # 2d) 검증 후 임시 DB 정리 (선택)
    docker compose -f infra/docker-compose.yml exec -T postgres \
      psql -U denvia -d postgres -c "DROP DATABASE denvia_verify;"
    ```
  - 백업 보관 정책: 최소 30일 보관, 월간 백업은 1년 보관(NFR-S7 감사 로그 보관 정책에 준함).

### 2.2 Sentry 에러 로그 리뷰

- 환경변수 `SENTRY_DSN_API` / `SENTRY_DSN_WEB`(`.env.example` 참조)에 등록된 Sentry 프로젝트 대시보드 접속.
- 주간 리뷰 항목:
  - **이슈 발생 추이**: 새 이슈 vs 기존 이슈 빈도
  - **5xx 비율**: 1% 초과 시 즉시 §RUNBOOK_INCIDENT 시나리오 ③(OpenAI 장애 가능성) 검토
  - **PII 누설 경고**: structlog masking 누락 의심 항목 — 즉시 마스킹 수정 후 재배포

### 2.3 주간 예산 사용량 검토

- 접근: `/admin/finance/budget` **(TBD — Story 5.2 backlog)**
- 임시 SQL 조회:
  ```sql
  -- 이번 달 누적 토큰 비용 추정 (USD)
  -- ⚠️ 단가는 OpenAI 가격 페이지(https://openai.com/api/pricing) 기준
  --    아래 상수는 'gpt-4o-mini' 2026-04 기준 (input $0.150/1M, output $0.600/1M)
  --    모델 변경 또는 OpenAI 가격 개정 시 본 SQL 갱신 필수
  SELECT
    SUM(prompt_tokens) * 0.00000015 AS prompt_cost_usd,      -- gpt-4o-mini input
    SUM(completion_tokens) * 0.00000060 AS completion_cost_usd  -- gpt-4o-mini output
  FROM qa_logs
  WHERE created_at >= DATE_TRUNC('month', NOW());
  -- (TBD: qa_logs 테이블 미생성 — Story 2.1)
  -- (TBD: 사용 모델은 Story 8.4 admin/rag/model-tuning에서 동적 변경 가능 → 그 후엔 모델별 단가 조회로 변경)
  ```
- 80% 도달 전 추세이면 §3.2 월간 예산 한도 재설정 검토.

---

## 3. 월간 작업

매월 1일 오전 **30분** 내 완료한다.

### 3.1 월매출 리포트 — Excel export

- 접근: `/admin/finance/revenue` → "Excel 다운로드" 버튼 **(TBD — Story 5.5, HOLD-PG 의존)**
- 본 기능은 결제 게이트웨이(PG) 연동(Epic 3) 완료 후 활성화되므로, 현 시점에는 수행하지 않는다.
- 인수 시점에 PG 연동 완료(`PG_PROVIDER=toss` — 메모리 `project_pg_vendor_toss.md` 참조)되면 본 절차 활성화.

### 3.2 월 예산 한도 재설정

- 접근: `/admin/settings` → "월간 예산 한도(USD)" 입력 **(TBD — Story 7.4 backlog)**
- 결정 기준:
  - 전월 사용률이 80% 미만이었으면 한도 유지
  - 80~95% 였으면 +10% 상향 검토
  - 95% 초과 또는 100% 도달 이력이 있으면 +20% 상향 또는 운영 정책 재검토(§5 kill-switch 운용 정책 점검)

### 3.3 이용약관 변경 주기 확인

- 약관 위치: `docs/legal/terms.md` **(TBD — Story 9.2 범위)**
- 변경이 필요한 경우(예: kill-switch 자동 연장 조항 갱신, 결제 정책 변동):
  1. 변경 PR 생성
  2. 사용자 공지 발송 — `/admin/content` 공지 작성(Story 7.1, **TBD**)
  3. 약관 동의 재요청 정책에 따라 사용자 재동의 플로우 트리거

---

## 4. 재인덱싱 실행 가이드

본 절차는 RAG 지식베이스(TXT 파일) 변경 후 FAISS 인덱스를 전체 재빌드하는 절차다.

> **(TBD — Story 8.1·8.2·8.3 backlog)**: 현 시점 RAG 관리자 UI 및 FAISS 스왑 로직이 미구현이다. 본 가이드는 Story 8.1~8.3 완료 후 정식 활용된다.

### 4.1 사전 준비

- TXT 파일 포맷 요구(Story 8.1 명세):
  ```
  {대분류}
  ==중분류==
  본문 내용...
  ```
- 파일 인코딩: UTF-8(BOM 없음)
- 한 파일당 최대 크기: 10MB(Story 8.1 검증 규칙)

### 4.2 업로드·검증·재빌드 순서

1. **업로드**: `/admin/rag/data` → "TXT 업로드" 버튼 → 파일 선택
2. **포맷 검증(dry-run)**: 업로드 직후 자동 실행. 통과 시 미리보기 화면에 청크(chunk) 수·예상 토큰 표시.
3. **재빌드 트리거**: "전체 재빌드" 버튼 클릭 → 관리자 비밀번호 재확인 모달
4. **진행률 모니터링**: SSE(Server-Sent Events) 채널 `admin:events`의 `rag_rebuild_progress` 이벤트로 실시간 진행률(%) 표시

### 4.3 야간 실행 권장(NFR-SC3)

- **권장 시간:** **22:00 KST 이후**
- **사유:**
  - FAISS 인덱싱 중 메모리 피크 발생(전체 청크 임베딩 시점) → Oracle Compute VM(NFR-SC3 인프라 트리거 임계 청크 수 ≥ 10만)에서 OOM(Out of Memory) 위험.
  - 사용자 질의 응답 지연 가능성(p95 응답 시간 일시 상승).
  - `index_a` ↔ `index_b` 스왑 순간(<1초)이지만 야간 트래픽 최저 시간대에 수행하면 영향 최소화.
- **트래픽 임계치:** 청크 수가 10만을 초과하거나 전체 재빌드 소요 시간이 30분 이상이면 §RUNBOOK_INCIDENT 시나리오 ⑦(Oracle VM 다운 — NFR-SC3 트리거) 평가 필요.

### 4.4 재빌드 완료 검증

- 완료 알림톡 수신: 카테고리 `system`, 템플릿 `admin.rag_rebuild_completed` **(TBD — Story 8.3에서 템플릿 추가)**
- `current` symlink 변경 확인:
  ```bash
  docker compose -f infra/docker-compose.yml exec api ls -la /workspace/rag/data/faiss/current
  # 변경 전: index_a → 변경 후: index_b (또는 그 반대)
  ```
- 사용자 질의 1건 시험: `/qa` 화면에서 새 지식 반영 확인.

---

## 5. kill-switch 운용 SOP

본 절차는 비상 정지 스위치(kill-switch)의 두 모드(자동·수동) 운용 가이드다. 결정 근거는 [`./adr/0001-ssot-deviations.md`](./adr/0001-ssot-deviations.md) 편차 #4를 참조한다.

> **(TBD — Story 9.2 backlog)**: `killswitch_states` 테이블·`KillSwitchPanel` UI·`/admin/finance/killswitch` 라우트가 모두 미구현. 본 SOP는 문서상 절차 검토용이며 실 발동은 Story 9.2 완료 후 가능하다.

### 5.1 두 모드 결정 기준

| 모드 | 발동 시점 | 차단 범위 | 발동 주체 |
|---|---|---|---|
| `auto_free_only` | 월 예산 100% 도달 시 시스템 자동 ON | 무료 사용자 질의만(429 `BUDGET_HARD_CAP_REACHED`) — 유료 구독자 정상 | 시스템(`activated_by_admin_id=NULL`) |
| `manual_total` | 관리자 비상 판단 시 수동 발동 | 유료·무료 모두 차단 | 관리자(`activated_by_admin_id` 기록) |

**평가 규칙 (모드별 차단 대상의 합집합):**
- 무료 사용자: `auto_free_only` 또는 `manual_total` 중 하나라도 ON이면 차단
- 유료 사용자: `manual_total` ON일 때만 차단
- **관리자(`role='admin'`)**: kill-switch 적용 **제외** — 인시던트 진단 중 관리자 본인이 질의 테스트할 수 있어야 함. 차단 판정 미들웨어가 `request.user.role == 'admin'`이면 bypass.

(이전 표현 "OR 평가 + 상위집합" 표현은 본 정의로 대체. 구현자는 `if user.role == 'admin': allow; elif manual_total: deny; elif auto_free_only and user.subscription == 'free': deny; else: allow` 패턴 사용.)

### 5.2 `manual_total` 발동 절차

1. **판단**: 다음 중 하나에 해당하는 경우만 발동
   - 보안 인시던트(예: 대량 어뷰징·DDoS·계정 탈취 의심)
   - 데이터베이스 또는 RAG 인프라 심각 장애로 잘못된 답변이 사용자에게 노출될 위험
   - 법적 요구(예: 행정청 일시 중단 요청)
2. **2단계 확인**:
   - Step A: `/admin/finance/killswitch` → "수동 전체 정지" 버튼 클릭
   - Step B: 관리자 비밀번호 재입력 + 사유(`reason TEXT`) 필수 기재(최소 20자)
   - **약관 가드**: `docs/legal/terms.md`(Story 9.2 범위, 현 시점 미작성) 미완료 상태에서는 비상시 외 발동 자제 — 유료 구독 자동 연장 정책의 법적 근거가 약관에 명시되어야 분쟁 회피 가능
3. **즉시 알림톡 발송 확인**: 본인 휴대폰으로 `admin.killswitch_manual_activated` 수신 확인.
   - **알림톡 미수신 시 fallback 검증**: 알림톡 공급자 자체 장애 가능성 → DB와 structlog로 발동 성공 확인
     ```sql
     -- 발동 직후 활성 row 확인
     SELECT mode, activated_at, activated_by_admin_id, reason
     FROM killswitch_states
     WHERE deactivated_at IS NULL AND mode = 'manual_total'
     ORDER BY activated_at DESC LIMIT 1;
     ```
     ```bash
     # structlog 발동 이벤트 확인
     docker compose -f infra/docker-compose.yml logs api | grep "killswitch.manual_total.activated"
     ```
   - 발동 확인 안 되면 재클릭 금지(`uq_killswitch_active_mode` 위반 위험) — 위 SQL/log로 상태 먼저 확정
4. **사용자 영향**: 모든 `/qa/stream` 요청이 503 `SERVICE_UNAVAILABLE` 응답으로 차단되며 클라이언트는 메인터넌스 안내 화면으로 전환. 진행 중이던 SSE 스트림은 서버 측에서 즉시 종료(close on detect).

### 5.3 해제 후 유료 구독자 기간 자동 연장 확인

- 이용약관(`docs/legal/terms.md` — **TBD Story 9.2**) 명시 조항: 수동 kill-switch 발동 시 정지 기간(분 단위)만큼 유료 구독 만료일을 자동 연장.
- 해제 절차:
  1. `/admin/finance/killswitch` → "해제" 버튼
  2. 관리자 비밀번호 재입력
  3. 시스템이 자동으로 활성 유료 구독자 전체에 대해 `subscription.expires_at += (deactivated_at - activated_at)` 갱신
- 검증 절차:
  ```sql
  -- (a) 우선 killswitch_states에서 정지 기간 추출
  SELECT
    id AS killswitch_id,
    activated_at,
    deactivated_at,
    EXTRACT(EPOCH FROM (deactivated_at - activated_at)) / 60 AS stoppage_minutes
  FROM killswitch_states
  WHERE mode = 'manual_total'
    AND deactivated_at IS NOT NULL
  ORDER BY deactivated_at DESC
  LIMIT 1;
  -- 위에서 얻은 stoppage_minutes·deactivated_at 값을 (b)에 대입

  -- (b) 정지 기간 동안 유효했던 구독자 전수 확인 — LIMIT 없이 카운트로 검증
  WITH params AS (
    SELECT
      :stoppage_minutes::int AS stoppage_minutes,  -- (a)에서 얻은 값
      :deactivated_at::timestamptz AS deactivated_at
  )
  SELECT
    COUNT(*) FILTER (WHERE updated_at >= (SELECT deactivated_at FROM params)) AS extended_count,
    COUNT(*) AS total_active
  FROM subscriptions
  WHERE status = 'active';
  -- 기대: extended_count = 정지 기간 중 active였던 구독자 수와 일치
  -- 불일치 시 자동 연장 워커 누락 → 수동 보정 필요
  -- (TBD: subscriptions 테이블은 Story 3.x에서 생성 — HOLD-PG)
  ```

### 5.4 `auto_free_only` 자동 동작 확인

- 별도 발동 절차 없음. 월 예산이 100% 도달하면 워커가 자동으로 `killswitch_states` INSERT.
- 관리자 휴대폰으로 `admin.budget_hard_cap_reached` 알림톡 자동 수신.
- 익월 1일 또는 예산 한도 상향(§3.2) 시 시스템이 자동 해제.

---

## 6. 알림톡 템플릿 변경·공급자 교체 절차

본 절차는 알림톡 발송 시스템 운영 변경 시 사용한다.

### 6.1 알림톡 어댑터 구조 개요(Story 4.1 인용)

- 포트(추상 인터페이스): `api/src/integrations/messaging/port.py` — `MessagingProvider` Protocol
- 구현체: `api/src/integrations/messaging/adapters/`
  - `stub.py` — 개발/CI 기본값(structlog 로그만 출력)
  - `aligo.py` — Aligo 알림톡 공급자(HOLD-MSG 해제 후 실 구현체 확장 예정)
  - `nhn_cloud.py` — NHN Cloud 알림톡 공급자(HOLD-MSG 해제 후 실 구현체 확장 예정)
- 카탈로그: `api/src/integrations/messaging/templates.py` — `TEMPLATE_CATALOG` 딕셔너리(현재 10종 등재)

### 6.2 템플릿 추가·변경 절차

1. **카탈로그 수정**: `api/src/integrations/messaging/templates.py`의 `TEMPLATE_CATALOG`에 신규 키 추가.
   - 키 형식: `{category}.{action}` (예: `billing.refund_partial`)
   - 카테고리: `BILLING` / `SUBSCRIPTION` / `NOTICE` / `SYSTEM` 중 하나
   - `URGENT_CATEGORIES`(billing·subscription·system)는 야간(21~08 KST) 차단 예외 — 신규 카테고리 추가 시 야간 정책 결정 필수.
2. **변수 정의**: `variables: list[str]`에 본문 치환 변수명 명시.
3. **공급자 콘솔 등록**: 카카오 비즈메시지 콘솔(또는 공급자 콘솔)에서 템플릿 사전 등록 후 승인 코드 발급(예: `KA01234`).
4. **환경변수 매핑 갱신**: `.env`의 `ALIMTALK_TEMPLATE_MAP_JSON` 갱신.
   ```bash
   # 예시
   ALIMTALK_TEMPLATE_MAP_JSON='{"billing.refund_partial": "KA09876", "billing.first_charge_success": "KA01234"}'
   ```
5. **API 컨테이너 무중단 적용 (graceful)**:
   - 환경변수 변경은 컨테이너 재시작이 필요하지만 `restart`는 진행 중 SSE 스트림·Celery 태스크를 끊는다.
   - **권장 시간대**: 야간 22:00 KST 이후 또는 트래픽 최저 시간대.
   - **사용자 공지**: §SECURITY §2.3.1 대체 채널 활용 (메인터넌스 페이지 또는 Story 7.2 popup).
   - **순차 적용**:
     ```bash
     # 1) beat 먼저(스케줄러 — 즉시 끊겨도 영향 작음)
     docker compose -f infra/docker-compose.yml restart beat

     # 2) worker (대기 중 태스크 완료 후 종료 — graceful)
     docker compose -f infra/docker-compose.yml exec worker celery -A api.src.workers.celery_app control shutdown
     docker compose -f infra/docker-compose.yml up -d worker

     # 3) api 마지막 (사용자 영향 큼 — 트래픽 최저 시간대)
     docker compose -f infra/docker-compose.yml restart api
     ```
6. **stub 환경 검증**: `MESSAGING_PROVIDER=stub`인 채로 1건 발송 후 structlog 출력에 `template_code` 정상 표시 확인.

### 6.3 공급자 교체 절차(stub → aligo / nhn_cloud)

> **HOLD-MSG 해제 전제 조건**: 클라이언트가 알림톡/SMS 공급자(Aligo 또는 NHN Cloud) 계약 후 API 키 제공.

1. **`.env` 변경**:
   ```bash
   MESSAGING_PROVIDER=aligo  # 또는 nhn_cloud
   # 신규 환경변수 추가 (공급자별 키)
   ALIGO_API_KEY=...
   ALIGO_USER_ID=...
   # 또는
   NHN_APP_KEY=...
   NHN_SECRET_KEY=...
   ```
2. **어댑터 실 구현체 작성**: 현 `aligo.py`·`nhn_cloud.py`는 모든 메서드가 `NotImplementedError`를 던지는 스켈레톤 상태. HOLD-MSG 해제 후 다음 메서드 3종을 채운다.
   - `send_sms_otp(phone, code)` — OTP SMS 발송(평문 OTP 절대 로그 금지, 마스킹은 `_mask_phone` 활용)
   - `send_sms(phone, body)` — LMS 형식 SMS(폴백 경로)
   - `send_alimtalk(recipient_phone, template_code, variables)` — `AlimtalkResult` 반환
3. **HOLD-MSG 해제 후 본 문서 갱신 필수**: 본 §6 절차에 실 구현체 사용 시 주의사항(rate limit·재시도 정책·에러 코드 매핑) 추가.
4. **단계적 전환**:
   - Day 1: `MESSAGING_PROVIDER=aligo`로 전환 후 stub 환경 대비 발송 성공률 모니터링(structlog 기반).
   - Day 7: 정상이면 stub 어댑터 코드 보존(롤백 경로 유지).

### 6.4 알림톡 발송 실패 시 SMS 자동 폴백

- 알림톡 발송이 공급자 측 오류(예: 템플릿 미일치·차단 번호)로 실패하면 자동으로 LMS SMS로 폴백 발송(Story 4.1 정책).
- 폴백 발송도 실패하면 `notification_queue.status='failed'` 행으로 영구 기록 → §RUNBOOK_INCIDENT 시나리오 ② 진단 절차 수행.

---

## 검증 이력

| 날짜 | 검증자 | 결과 | 조치 |
|---|---|---|---|
| 2026-04-28 | Codex | 문서 정합성 업데이트 — Story 5.1 구현 상태를 반영해 `/admin/dashboard` backlog 표현을 `/admin` shell 구현 완료 + KPI 위젯 Story 5.2~5.5 대기 상태로 분리. | Story 5.2 완료 후 KPI 위젯 기반 절차로 §1.1 재검증 |
| 2026-04-24 | Hyung woo | OK — 6개 섹션 모두 게재 확인. 인용 파일 경로(`api/src/integrations/messaging/{port,templates,adapters/stub,adapters/aligo,adapters/nhn_cloud}.py`·`infra/docker-compose.yml`·`.env.example`) 모두 실재 검증. 당시 미존재 항목(`infra/scripts/backup-postgres.sh`·`/admin/dashboard`·`/admin/finance/budget`·`/admin/rag/data`·`/admin/finance/killswitch`·`/admin/settings`·`docs/legal/terms.md`·`qa_logs`·`subscriptions`·`killswitch_states` 테이블)은 모두 `(TBD — Story X.Y)` 표기로 명시. | — |
| 2026-04-24 | Hyung woo (Story 9.4 AC-7 시나리오 ② Dry-run) | 보류 (Story 9.2 backlog) — `manual_total` kill-switch 발동·해제 절차는 본 문서 §5.2·§5.3에 문서화 완료. 실 발동은 `killswitch_states` 테이블·`KillSwitchPanel` UI·`/admin/finance/killswitch` 라우트가 모두 Story 9.2 범위로 미구현 → 문서상 절차 검토만 수행. 본 SOP의 절차(2단계 확인·사유 필수 기재·해제 후 유료 구독자 기간 자동 연장)는 Story 9.2 ACs(L2587-2733 범위)와 일치 확인. | Story 9.2 완료 후 Staging 환경에서 실전 발동·해제 Dry-run 필수 |
| 2026-04-24 | Hyung woo (Story 9.4 AC-7 시나리오 ③ Dry-run) | 보류 (인프라 환경 사유) — pg_dump·pg_restore 절차는 본 문서 §2.1 + RUNBOOK_INCIDENT 시나리오 ⑦에 문서화 완료. 호스트 Docker daemon 미기동(`Docker Desktop` 실행 필요)으로 실 컨테이너 기동·실 백업·복원 Dry-run 보류. 명령어 문법(`docker compose ... exec -T postgres pg_dump -U denvia ...`) 자체는 표준 PostgreSQL 16 문법과 일치 확인. | 인수 시점에 Docker 환경 기동 후 §2.1 명령으로 백업 1회 + 임시 DB에 복원 + `SELECT count(*) FROM users` 무결성 검증 수행 |
| 2026-04-24 | claude-opus-4-7 (code-review 후속 9건 patch 적용) | OK — §1.1(±30% 변동률 SQL + §⑥ 매핑), §1.2.1(SMS 폴백 검증), §2.1(pg_dump --clean 위험 안내 + 별도 빈 DB 복원 무결성 검증), §2.3(USD 토큰 모델 명시), §5.1(평가 규칙 단순화 + admin bypass), §5.2(약관 가드 + 알림톡 미수신 fallback), §5.3(SQL 플레이스홀더 추출 + 카운트 검증), §6.2(graceful 순차 재시작) 적용 완료 | — |
