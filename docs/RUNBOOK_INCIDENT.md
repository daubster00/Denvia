# RUNBOOK_INCIDENT — Denvia 이상 대응 플레이북

> **최종 수정일:** 2026-04-24
> **작성자:** Hyung woo
> **승인자:** (인수자 검토 시 기입)
> **버전:** v1.0
> **관련 FR/Story:** FR55·FR56·NFR-SC3 / Story 9.4

본 플레이북은 Denvia 운영 중 발생할 수 있는 **7가지 대표 이상 시나리오**에 대한 표준 대응 절차를 정의한다. 각 시나리오는 **`증상 → 진단 → 조치 → 에스컬레이션`** 4단계 구성이다.

> **공통 재시도 정책(AR12 인용):** 본 플레이북에 등장하는 외부 의존(PG·알림톡 공급자·OpenAI)은 모두 `tenacity` 기반 **3회 지수 백오프** 정책을 따른다 — `min=2초`, `max=30초`, `multiplier=2`.

---

## 시나리오 ① — 결제 장애: F-204 재시도 반복 실패

> **(TBD — Epic 3 전반 HOLD-PG)**: 본 시나리오는 Story 3.4(결제 실패 재시도) 완료 후 활성화된다. 현 시점에는 문서상 절차 검토용.

### 증상

- 사용자 알림톡 카테고리 `billing.retry_failed_3`("결제 최종 실패") 수신 빈도 급증
- 관리자 대시보드(`/admin/finance` — TBD Story 9.1)에서 `payments.status='failed'` 누적 카운터 상승
- Sentry에 `BillingError` 또는 PG 어댑터(예: 토스 페이먼츠) 5xx 발생률 상승

### 진단

1. PG 공급자 콘솔(`PG_PROVIDER=toss` — 메모리 `project_pg_vendor_toss.md` 참조) 접속하여 일별 거래 성공률 확인
2. 데이터베이스 직접 조회(현 시점 임시):
   ```sql
   -- 최근 24시간 결제 실패 분포 (TBD: payments 테이블은 Story 3.x에서 생성)
   SELECT
     pg_error_code,
     COUNT(*) AS cnt
   FROM payments
   WHERE status = 'failed' AND created_at >= NOW() - INTERVAL '24 hours'
   GROUP BY pg_error_code
   ORDER BY cnt DESC;
   ```
3. 토스 페이먼츠 에러 코드 분류:
   - `PAY_PROCESS_CANCELED` — 사용자 취소(시스템 이상 아님, 무시)
   - `INVALID_CARD` — 카드 정보 오류(사용자 카드 변경 안내)
   - `PROVIDER_ERROR` — PG 공급자 측 장애(공급자 상태 페이지 확인)

### 조치

1. **3회 재시도 정책 확인**: D+1 / D+3 / D+7 지수 백오프 모두 실패한 사용자 식별
   ```sql
   SELECT user_id, payment_id, retry_count, last_error_code
   FROM payments
   WHERE status = 'failed' AND retry_count >= 3 AND created_at >= NOW() - INTERVAL '7 days';
   ```
2. **수동 환불 큐 생성**: `manual_refund_queue` 테이블에 INSERT(Story 3.6 / Story 9.3 범위)
3. **고객 알림톡 발송**: 템플릿 `billing.refund_pending_review` (TBD — Story 3.6에서 추가)로 수동 검토 진행 안내
4. **카드 정보 갱신 유도**: `INVALID_CARD` 에러 군은 `/mypage/payment-method` 갱신 링크를 알림톡으로 안내(Story 4.4 — TBD)

### 에스컬레이션

- 1시간 내 PG 공급자 측 장애로 판명되면: PG 공급자 기술 지원 채널 즉시 연락 + 자체 메인터넌스 배너 노출(Story 7.2 — TBD)
- 시간당 결제 실패율 50% 초과 지속 시: `manual_total` kill-switch 발동 검토(§OPERATIONS §5.2)
- 클라이언트 보고: 인수자 휴대폰 번호 — **(인수자 기입)**

---

## 시나리오 ② — 알림톡 공급자 장애: SMS 폴백 확인

### 증상

- `notification_queue.status='failed'` 행 시간당 30건 이상 급증
- 관리자 휴대폰으로 시스템 알림톡(예: `admin.budget_warning_*`) 미수신
- Sentry에 `AlimtalkProviderError` 또는 어댑터(`api/src/integrations/messaging/adapters/aligo.py` 또는 `nhn_cloud.py`) 5xx 급증

### 진단

1. 공급자 콘솔 상태 페이지 확인(Aligo / NHN Cloud)
2. 데이터베이스 조회:
   ```sql
   -- 최근 1시간 알림톡 발송 실패 통계
   SELECT
     channel,           -- 'alimtalk' | 'sms'
     status,            -- 'pending' | 'sent' | 'failed' | 'fallback_sent'
     COUNT(*) AS cnt
   FROM notification_queue
   WHERE created_at >= NOW() - INTERVAL '1 hour'
   GROUP BY channel, status;
   ```
3. SMS 폴백 작동 검증:
   ```sql
   -- 알림톡 실패 → SMS 폴백 성공률
   SELECT
     COUNT(*) FILTER (WHERE status = 'fallback_sent') AS fallback_ok,
     COUNT(*) FILTER (WHERE status = 'failed') AS total_failed
   FROM notification_queue
   WHERE channel = 'alimtalk' AND created_at >= NOW() - INTERVAL '1 hour';
   ```
4. structlog에서 `messaging.{provider}.send_alimtalk.error` 로그 추출하여 에러 메시지·HTTP 상태 코드 분석

### 조치

1. **재시도 정책 확인**: `tenacity` 3회 지수 백오프(min=2, max=30) 모두 실패한 메시지는 `notification_queue.status='failed'` 행으로 영구 기록 → 폴백 워커가 SMS 재발송 시도
2. **임시 공급자 전환**(다중 공급자 계약 시):
   ```bash
   # .env
   MESSAGING_PROVIDER=nhn_cloud  # aligo → nhn_cloud (또는 그 반대)
   docker compose -f infra/docker-compose.yml restart api worker beat
   ```
3. **stub 어댑터 임시 전환 금지**: 운영 환경에서 `MESSAGING_PROVIDER=stub`로 전환하면 발송이 무음으로 사라짐. 절대 사용 금지.
4. **수동 재발송 큐 처리**: `notification_queue.status='failed'` 행은 공급자 복구 후 워커가 자동 재시도하지 않으므로, 수동 재시도 스크립트 필요(`api/scripts/retry_failed_notifications.py` — **TBD**, HOLD-MSG 후 추가).

### 에스컬레이션

- 1시간 내 미복구 시: 공급자 기술 지원 채널 연락 + 두 번째 공급자 계약 검토
- 24시간 미복구 + SMS 폴백마저 실패하면: `manual_total` kill-switch 발동 검토(공지 채널 부재 상태)
- 클라이언트 보고: 인수자 휴대폰 번호 — **(인수자 기입)**

---

## 시나리오 ③ — OpenAI API 장애

### 증상

- `/qa/stream` 엔드포인트 5xx 응답률 급증
- Sentry에 `openai.APIError` / `openai.RateLimitError` 빈도 상승
- 사용자 측에서 "답변 생성 중 오류가 발생했습니다" 카피 노출 빈도 증가

### 진단

1. OpenAI 상태 페이지(`https://status.openai.com`) 확인 — 본 URL은 **사용자 또는 인수자 직접 접속 권장**(자동 호출 금지, 본 문서에서 인용만)
2. Sentry 5xx 분포 확인:
   - `RateLimitError` (HTTP 429) — 분당 요청 한도 초과
   - `APIError` (HTTP 5xx) — OpenAI 측 일시 장애
   - `Timeout` — 응답 지연
3. 자체 재시도 정책 확인: `tenacity` 3회 지수 백오프(min=2, max=30) — 3회 모두 실패하면 사용자에게 5xx 노출

### 조치

1. **메인터넌스 배너 노출**: `/admin/content/popups` (TBD — Story 7.2)에서 시스템 점검 안내 팝업 활성화. 디스클레이머 강화 카피:
   > "AI 답변 생성 시스템에 일시적인 장애가 발생했습니다. 현재 답변 결과는 의료 자문이 아니며 이용에 참고만 해주십시오. 시스템 복구 즉시 정상 서비스됩니다."
2. **단기 우회 (사용자 영향 큼 — 사전 공지 필수)**: 무료 사용자 일일 쿼터를 임시 0으로 하향 조정(Story 7.4 — TBD) → 유료 사용자 응답률 우선 확보
   - **공지 절차**: kill-switch 발동(§OPERATIONS §5.2)과 동일한 사용자 영향도 → 다음을 함께 수행
     - (a) Story 7.2 popup 활성화 ("OpenAI 일시 장애로 무료 답변이 일시 중단됩니다")
     - (b) `/qa` 화면 상단 배너 (web 클라이언트 patch 또는 메인터넌스 페이지)
     - (c) 조치 후 24시간 내 정상화되지 않으면 클라이언트(인수자) 보고
   - **재시도 비용 폭증 가드**: tenacity 재시도가 토큰을 추가 소비 → 1시간 내 미복구 시 `OPENAI_RETRY_DISABLED=true` 임시 환경변수로 재시도 0회 전환 검토 (Story 2.x에서 환경변수 추가 필요)
3. **로그 보강**: structlog `qa.openai.error` 로그 카운트로 복구 시점 측정

### 에스컬레이션

- 30분 내 미복구 시: `manual_total` kill-switch 발동 검토(잘못된 답변 노출 방지)
- API 키 원인(401 Unauthorized)이면: 즉시 새 API 키 발급 후 `.env`의 `OPENAI_API_KEY` 갱신 + 컨테이너 재시작
- 클라이언트 보고: 인수자 휴대폰 번호 — **(인수자 기입)**

---

## 시나리오 ④ — 재빌드 실패·partial 인덱스 잔존

> **(TBD — Story 8.3 backlog)**: FAISS 스왑 로직 미구현. 본 시나리오는 Story 8.3 완료 후 정식 활용.

### 증상

- `/admin/rag/data` 재빌드 진행 중 SSE 채널의 `rag_rebuild_progress` 이벤트가 50~99% 구간에서 정지
- `rebuild_jobs.status='failed'` 행 발생 (Story 8.3 테이블 — TBD)
- FAISS `current` symlink가 신규 인덱스가 아닌 **이전 인덱스를 그대로 가리키는** 상태(스왑 실패)
- 디스크에 `index_a` / `index_b` 외 `index_a.partial` 또는 `index_b.partial` 잔존 디렉터리 존재

### 진단

1. 재빌드 작업 로그 확인:
   ```sql
   SELECT id, status, error_message, started_at, finished_at
   FROM rebuild_jobs
   ORDER BY started_at DESC LIMIT 5;
   -- (TBD: rebuild_jobs 테이블은 Story 8.3에서 생성)
   ```
2. `utils/faiss_swap.py` (Story 8.3 — TBD) 로그를 structlog `rag.swap.error` 키로 추출
3. 디스크 상태 확인:
   ```bash
   docker compose -f infra/docker-compose.yml exec api ls -la /workspace/rag/data/faiss/
   # current → index_a (예전 인덱스 그대로) + index_b.partial (재빌드 중간 산물 잔존)
   ```

### 조치

1. **이전 인덱스 롤백**: `current` symlink가 이미 정상 인덱스를 가리키므로 사용자 영향 없음. 별도 조치 불필요.
2. **partial 디렉터리 정리**:
   ```bash
   docker compose -f infra/docker-compose.yml exec api rm -rf /workspace/rag/data/faiss/index_b.partial
   ```
3. **원인 분석**: `rebuild_jobs.error_message` 검토
   - `OOM` → 청크 수가 NFR-SC3 임계(10만)를 초과한 가능성 → §⑦ 시나리오 평가
   - `EmbeddingAPIError` → OpenAI 임베딩 API 장애 → §③ 시나리오 평가
   - `DiskFull` → 호스트 디스크 용량 확보 후 재시도
4. **재시도**: 원인 해소 후 `/admin/rag/data` "전체 재빌드" 재실행

### 에스컬레이션

- 3회 연속 재빌드 실패 시: NFR-SC3 인프라 트리거 평가(§⑦)
- `current` symlink가 손상되어 질의 차단 발생 시: `manual_total` kill-switch 발동 후 수동 복구
- 클라이언트 보고: 인수자 휴대폰 번호 — **(인수자 기입)**

---

## 시나리오 ⑤ — 예산 soft/hard cap 도달

> 결정 근거: [`./adr/0001-ssot-deviations.md`](./adr/0001-ssot-deviations.md) 편차 #4(kill-switch 이원화).

### 증상

- 관리자 휴대폰으로 알림톡 수신:
  - 80% 도달: `admin.budget_warning_80` (TBD — Story 5.2 템플릿)
  - 95% 도달: `admin.budget_warning_95`
  - 100% 도달: `admin.budget_hard_cap_reached` + `auto_free_only` 자동 ON
- `/admin/finance/budget`(TBD — Story 5.2)에서 `status='warning'` 또는 `'critical'` 표시

### 진단

1. 알림 시점 확인:
   ```sql
   SELECT year_month, monthly_limit_usd, spent_usd, percent,
          warning_80_sent_at, warning_95_sent_at, killswitch_triggered_at
   FROM budget_thresholds
   WHERE year_month = TO_CHAR(NOW(), 'YYYY-MM');
   -- (TBD: budget_thresholds 테이블은 Story 5.2에서 생성)
   ```
2. 단기 사용량 폭증 원인 분석:
   - 일별 토큰 사용량 추이(`qa_logs` — TBD Story 2.1)
   - 단일 계정 남용 의심 시 § ⑥ 시나리오 평가
3. `auto_free_only` 활성 상태 확인:
   ```sql
   SELECT mode, activated_at, deactivated_at, year_month
   FROM killswitch_states
   WHERE deactivated_at IS NULL;
   -- (TBD: killswitch_states 테이블은 Story 9.2에서 생성)
   ```

### 조치

#### 80% 알림 수신 시

- 잔여 예산 분포 확인 → 익월까지 충분하면 모니터링만 강화
- 필요 시 §3.2 월간 예산 한도 임시 +10% 상향 검토

#### 95% 알림 수신 시

- 일별 사용량이 예상치 초과면: `/admin/settings`(TBD — Story 7.4)에서 무료 사용자 일일 쿼터 임시 하향(예: 3건 → 1건)
- 단일 계정 남용이 원인이면: § ⑥ 시나리오의 수동 차단 경로 적용

#### 100% 도달 (`auto_free_only` 자동 ON)

- 시스템이 자동 처리하므로 즉각적 수동 조치 불필요
- 확인 사항:
  - 무료 사용자 차단 정상 작동(429 `BUDGET_HARD_CAP_REACHED`)
  - 유료 사용자 정상 응답
- 익월 1일 또는 예산 한도 상향 시 `auto_free_only` 자동 해제

### 에스컬레이션

- `manual_total` 발동 기준: 단순 예산 초과만으로는 발동 부적절(자동 차단으로 충분). 다음 경우만 발동:
  - 결제 청구가 즉각 현금 유출로 이어지는 비즈니스 위험(예: 사용량 폭증으로 청구액이 월간 예산의 200% 초과 우려)
  - 보안 인시던트 의심(어뷰징·계정 탈취)
- 클라이언트 보고: 100% 도달 시 자동 알림톡으로 충분. 추가 보고는 인수자 판단.

---

## 시나리오 ⑥ — 이상탐지 급증

> **(TBD — Epic 6 Story 6.5 backlog)**: `anomaly_events` 테이블·이상탐지 워커 미구현. 본 시나리오는 Story 6.5 완료 후 활성화.

### 증상

- 관리자 SSE 채널 `admin:events`의 `anomaly_alert` 이벤트 빈도 시간당 30건 초과
- `anomaly_events` 테이블에 `severity='high'` 행 누적
- `/admin/users` (TBD — Story 6.1)에서 단일 계정의 24시간 질의 수가 정상 분포(p99) 대비 10배 초과

### 진단

1. 이상 이벤트 분포 분석:
   ```sql
   SELECT
     event_type,        -- 'rapid_query' | 'multi_account' | 'token_burst' 등
     severity,
     COUNT(*) AS cnt
   FROM anomaly_events
   WHERE created_at >= NOW() - INTERVAL '1 hour'
   GROUP BY event_type, severity
   ORDER BY cnt DESC;
   -- (TBD: anomaly_events 테이블은 Story 6.5에서 생성)
   ```
2. 단일 계정 남용 vs 전체 트래픽 이상 구분:
   - **단일 계정 남용**: 상위 5명 사용자가 전체 이상 이벤트의 80% 이상 차지 → § "수동 차단" 경로
   - **전체 트래픽 이상**: 이상 이벤트가 사용자 전반에 균등 분포 → DDoS 또는 봇 트래픽 의심

### 조치

#### 단일 계정 남용 (수동 차단)

1. `/admin/users/{user_id}` (TBD — Story 6.2) 진입
2. "차단(blocked)" 버튼 → 사유(`reason TEXT`) 필수 기재
3. 차단 시 사용자 측은 모든 API 요청에 403 `ACCOUNT_BLOCKED` 응답
4. `audit_logs`에 액션 코드 `admin.user.blocked` 기록(NFR-S7, 1년 보관)

#### 전체 트래픽 이상 (DDoS 의심)

1. Nginx IP/대역 차단 — **`infra/nginx/snippets/blocked-ips.conf` (신설, SECURITY §7.2와 동일 경로)** 사용
   ```bash
   # blocked-ips.conf에 deny 라인 추가 후
   docker compose -f infra/docker-compose.yml exec nginx nginx -t          # 문법 검증 필수
   docker compose -f infra/docker-compose.yml exec nginx nginx -s reload   # 무중단 적용 (restart 금지 — SSE 끊김)
   ```
   상세 절차·해제 절차는 [`./SECURITY.md`](./SECURITY.md) §7.2 참조.
2. 의심 IP 대역 차단(Sentry RUM에서 비정상 분포 IP 식별) — 동일 snippets 파일에 대역 추가
3. 필요 시 `manual_total` kill-switch 발동 후 IP 차단 정책 적용

### 에스컬레이션

- 시간당 이상 이벤트 100건 초과 + 단일 IP 점유율 50% 초과 시: 즉시 `manual_total` 발동
- 결제 우회 시도(예: 동일 카드로 다중 계정 가입) 발견 시: 결제 거부 정책 적용 + 법무 검토 요청
- 클라이언트 보고: 인수자 휴대폰 번호 — **(인수자 기입)**

---

## 시나리오 ⑦ — Oracle VM 다운(NFR-SC3 트리거)

### 증상 — 다음 중 **1개 이상** 충족

- FAISS 청크 수 ≥ 10만(`SELECT COUNT(*) FROM rag_chunks` — TBD Story 8.1)
- 컨테이너 OOM 발생(`docker stats` 또는 호스트 dmesg 확인)
- `/qa/stream` p95 응답 시간 30초 초과 지속(Sentry RUM)
- Oracle Compute VM 인스턴스 상태 페이지에서 health-check fail

### 진단

1. **인프라 상태 확인**:
   ```bash
   # 컨테이너별 메모리·CPU 사용률
   docker stats --no-stream
   # 출력 예: api 컨테이너 mem_usage가 limit 90% 이상이면 임계 상태
   ```
2. **FAISS 메모리 점유 확인**:
   ```bash
   docker compose -f infra/docker-compose.yml exec api \
     python -c "import psutil; print(psutil.Process().memory_info().rss / 1024**2, 'MB')"
   ```
3. **Sentry RUM 응답 시간 분포**: p50 / p95 / p99 그래프 확인. p95가 30초 초과 지속이면 트리거.

### 조치

1. **즉시 임시 완화**:
   - 무료 사용자 일일 쿼터 0으로 하향(`/admin/settings` — TBD Story 7.4)
   - 의도적 지연(intentional delay) 시간 30초 → 60초 상향(무료 경로 트래픽 절감, Story 7.4 — TBD)
2. **유료 인프라 이전 의사결정**:
   - 본 트리거(NFR-SC3)는 "현재 인프라(Oracle Free Tier 4GB RAM·4OCPU)의 한계 도달" 신호
   - 결정 기준:
     - 청크 수 ≥ 10만이면 **확실 이전 권장** → Oracle Compute VM 유료 등급(8GB RAM 이상) 또는 AWS EC2(t3.medium 이상)
     - p95 응답 시간 임계 초과만 발생하면 우선 §④ FAISS 재빌드 시도 후 재평가
3. **이전 절차**(이전 결정 시):
   - 신규 인스턴스 프로비저닝 → `infra/docker-compose.prod.yml`로 배포 → 데이터베이스 마이그레이션 → DNS 전환

### 에스컬레이션 — 클라이언트 보고 템플릿

> **(인수자 기입 권장)**: 다음 템플릿은 클라이언트 보고용 표준 양식이다. 실제 발송 채널·담당자는 인수자가 결정.

```
[Denvia 운영 보고] NFR-SC3 인프라 트리거 발생

발생 일시: YYYY-MM-DD HH:MM KST
트리거 항목: (다음 중 해당 항목 ✓)
  □ 청크 수 10만 초과 (현재: ___개)
  □ 컨테이너 OOM 발생 (영향 컨테이너: ___)
  □ 질의 p95 응답 시간 30초 초과 지속 (현재: ___초)

영향:
  - 사용자 응답 지연 (체감 ___초)
  - 무료 사용자 차단 여부: ___
  - 유료 사용자 영향: ___

권고:
  - 임시 완화: 무료 쿼터 하향 적용 (적용 일시: ___)
  - 인프라 이전 권고: ___ (Oracle 유료 / AWS EC2)
  - 예상 비용: 월 USD ___

문의:
  - 운영 담당: (인수자 기입)
  - 기술 담당: (인수자 기입)
```

- 클라이언트 보고: 인수자 휴대폰 번호 — **(인수자 기입)**

---

## 검증 이력

| 날짜 | 검증자 | 결과 | 조치 |
|---|---|---|---|
| 2026-04-24 | Hyung woo | OK — 7개 시나리오 모두 4단계(증상·진단·조치·에스컬레이션) 구성 엄수. 인용 파일 경로(`api/src/integrations/messaging/adapters/{aligo,nhn_cloud,stub}.py`·`infra/docker-compose.yml`·`infra/nginx/denvia.conf`·`infra/docker-compose.prod.yml`·`.env.example`의 `OPENAI_API_KEY`·`PG_PROVIDER`·`MESSAGING_PROVIDER`) 모두 실재 검증. 미구현 시나리오 자원(`payments`·`subscriptions`·`notification_queue`·`rebuild_jobs`·`budget_thresholds`·`killswitch_states`·`anomaly_events`·`rag_chunks`·`qa_logs` 테이블 및 `/admin/*` 라우트군) 모두 `(TBD — Story X.Y)` 표기. `notification_queue`는 모델 파일(`api/src/models/notification_queue.py`) 실재 확인됨. | — |
| 2026-04-24 | Hyung woo (Story 9.4 AC-7 시나리오 ③ Dry-run 연계) | 보류 (인프라 환경 사유) — 시나리오 ⑦(Oracle VM 다운 — NFR-SC3 트리거)의 `docker stats` 명령은 호스트 Docker daemon 미기동으로 실 실행 보류. 명령어·SQL 문법은 모두 PostgreSQL 16·Docker 29.3.1 표준과 일치 확인. 클라이언트 보고 템플릿 양식 게재 확인. | 인수 시점에 Docker 환경 기동 후 `docker stats --no-stream`·`psutil` 메모리 측정 명령 실 실행 검증 |
| 2026-04-24 | claude-opus-4-7 (code-review 후속 3건 patch 적용) | OK — 시나리오 ③(메인터넌스 공지 절차 + 재시도 비용 폭증 가드), 시나리오 ⑥(snippets/blocked-ips.conf 경로 통일 + nginx -s reload + SECURITY §7.2 cross-link) 적용 완료 | — |
