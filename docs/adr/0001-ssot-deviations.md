# ADR-0001: SSOT 편차 6건 — 가입유형 권한·세그먼트 통합·아이디 찾기·kill-switch 이원화·환불 정책 부분환불 전환·다중 관리자 RBAC

> **최종 수정일:** 2026-05-26
> **작성자:** Hyung woo
> **승인자:** (인수자 검토 시 기입)
> **버전:** v1.2
> **관련 FR/Story:** FR10·FR11·FR17·FR19·FR28·FR29·FR55·FR56·FR58·FR59·FR60·FR61·FR62·FR63 / Story 1.3·1.5·1.6·3.3·3.4·3.6·4.3·4.4·5.2·6.2·6.4·9.2·9.3·9.4·10.1·10.2·10.3·10.4·10.5

---

본 ADR은 단일 진실 공급원(SSOT, Single Source of Truth: 클라이언트 측 기획서·기능명세서·협의서)과 PRD(Product Requirements Document) 사이의 **공식 편차 6건**을 정식 등재한다. 각 편차는 클라이언트와 합의·확정된 후 PRD에 반영되었으며, 본 ADR은 그 결정 경위와 영향 범위를 영구 기록으로 보존한다.

> ⚠️ **PRD 본문 정합성 주의:** 편차 #4(kill-switch)의 경우 `_bmad-output/planning-artifacts/prd.md` FR56 본문이 여전히 SSOT 초판 표현("유료 질의 전역 차단")으로 남아있다. **본 ADR이 정정 SSOT**이며, PRD 본문 교정은 Post-MVP 문서 유지보수 작업으로 분리한다.

---

## 편차 #1 — 가입유형 변경 권한(관리자만)

### 상태

**Accepted** (2026-04-22 클라이언트 확정)

### 맥락

SSOT 측 정의(F-106 / 협의서 #A-06):
- 사용자는 마이페이지에서 가입유형(치과의사·치과위생사·학생·기타)을 **30일 제한으로 직접 변경** 가능
- 연차(years_of_experience)는 **관리자만** 변경 가능

운영상 우려 사항:
- 가입유형 자가 변경은 무료/유료 정책 회피(예: 학생→일반 직군 또는 그 반대)·통계 왜곡·세그먼트 광고 타게팅 우회의 통로가 될 수 있다.
- 본 서비스의 사용자 등급은 결제·콘텐츠 차등의 핵심 축이므로 자가 변경은 운영 리스크가 크다.

### 결정

**가입유형(`segment`)·연차(`years_of_experience`) 모두 관리자만 변경 가능**으로 일원화한다. 사용자 마이페이지에서는 **조회만 가능**하다.

### 근거

- 운영 단순성: 30일 제한 로직(`segment_changed_at` 컬럼·쿨다운 검증 미들웨어) 불필요 → 코드 표면적 축소.
- 무결성: 결제·세그먼트 통계의 신뢰도 확보. 변경 이력은 `audit_logs` 테이블에 액션 코드 `admin.user.segment_changed`로 영구 보존(NFR-S7, 1년 보관).
- 사용자 영향 최소: 가입 단계에서 정확히 선택하면 변경 빈도는 매우 낮다는 클라이언트 운영 경험치(2026-04-22 미팅 기록).

### 영향받는 산출물

| 분류 | 항목 |
|---|---|
| PRD FR | FR11(가입유형 선택 — 관리자만 변경), FR28(마이페이지 조회만, 변경 비활성) |
| Epic/Story | Epic 6 Story 6.2 (`/admin/users` 권한·세그먼트 편집 UI) |
| 데이터베이스 | `users.segment`(이미 존재, `api/src/models/user.py:22`), `users.years_of_experience`(`api/src/models/user.py:23`) |
| 백엔드 | `api/src/routers/me.py`(마이페이지) — segment/years 수정 엔드포인트 **미제공** 보장 |
| 프론트엔드 | `web/src/features/account/`(현재 미구현, Story 4.3에서 신설 예정) — 조회 전용 UI |
| 관리자 UI | `web/src/features/admin-users/`(Story 6.2, TBD — 현 시점 backlog) |

### 날짜·승인자

2026-04-22 · Hyung woo(개발사) ↔ 클라이언트 합의 · ADR 등재일 2026-04-24

---

## 편차 #2 — 가입유형 3종 통합(학생·기타 단일 ③)

### 상태

**Accepted** (2026-04-22 클라이언트 확정)

### 맥락

SSOT 측 정의(F-106, 기능명세서 §2.2): 가입유형 4종 분류
1. 치과의사(`doctor`)
2. 치과위생사(`hygienist`)
3. 치위생학과 학생(`student`)
4. 기타(`other`)

운영상 검토:
- "치위생학과 학생"과 "기타"는 모두 **무료 등급 한정 사용자군**으로 결제·콘텐츠 정책이 동일하다.
- 두 분류를 별도로 유지할 운영 가치(통계·광고 타게팅·정책 분기)가 미미하다.
- 가입 폼 UX 단순화(4지선다 → 3지선다)로 가입 완료율 개선 효과 기대.

### 결정

가입유형을 **3종**으로 통합한다.

| 코드 | 한글명 | 결제 정책 |
|---|---|---|
| `doctor` | 치과의사 | Pro 구독 가능 |
| `hygienist` | 치과위생사 | Pro 구독 가능 |
| `student_other` | 학생/기타 | 무료 한정(구독 비활성) |

### 근거

- 운영 단순성: ENUM 분기·통계 집계 컬럼 1종 축소.
- UX 개선: 가입 폼 선택지 25% 축소(4→3).
- 손실 없음: 통계상 `student`·`other` 분리 분석 요구 부재(클라이언트 미팅 확인).

### 영향받는 산출물

| 분류 | 항목 |
|---|---|
| PRD FR | FR11(가입유형 선택 항목 정의) |
| Epic/Story | Epic 1 Story 1.3(이메일 가입 — segment 컬럼 입력), Epic 6 Story 6.4(세그먼트 통계 — 3종 카테고리) |
| 데이터베이스 | `users.segment`(`api/src/models/user.py:22`) — 현재 `String(20)`으로 정의되어 있어 ENUM 제약은 애플리케이션 레이어에서 관리 |
| 프론트엔드 | `web/src/features/auth/SegmentSelect.tsx`(존재 확인) — 3종 옵션만 노출 |
| 검증 로직 | `web/src/features/auth/schemas.ts`(존재 확인) — Zod enum `['doctor', 'hygienist', 'student_other']` |
| 데이터 마이그레이션 | 기존 `student`·`other` 값을 `student_other`로 정규화 (아래 SQL 참조) |

### 기존 데이터 마이그레이션 SQL

ADR 시행 시점에 이미 `users.segment IN ('student','other')` 행이 존재할 수 있다(개발 테스트 데이터·초기 가입자). `_VALID_SEGMENTS = {'doctor','hygienist','student_other'}` 검증 실패 방지를 위해 일회성 마이그레이션 또는 alembic data migration 필수.

```sql
-- 일회성 정규화 (BEGIN/COMMIT 트랜잭션으로 묶어 실행)
BEGIN;

-- (a) 영향 범위 사전 확인
SELECT segment, COUNT(*) AS cnt
FROM users
WHERE segment IN ('student', 'other')
GROUP BY segment;

-- (b) 정규화
UPDATE users
SET segment = 'student_other', updated_at = NOW()
WHERE segment IN ('student', 'other');

-- (c) 잔존 검증 (0건이어야 정상)
SELECT COUNT(*) AS leftover
FROM users
WHERE segment NOT IN ('doctor', 'hygienist', 'student_other');

COMMIT;
```

또는 alembic revision으로 멱등 처리(권장):
```python
# alembic/versions/00XX_normalize_segment_3types.py
def upgrade():
    op.execute("UPDATE users SET segment = 'student_other' WHERE segment IN ('student', 'other')")

def downgrade():
    # 단방향 정규화 — 원복 불가 (편차 #2가 student/other 분리 정보 손실 결정)
    pass
```

### 날짜·승인자

2026-04-22 · Hyung woo ↔ 클라이언트 · ADR 등재일 2026-04-24

---

## 편차 #3 — 아이디(이메일) 찾기 추가(FR10)

### 상태

**Accepted** (2026-04-22 클라이언트 확정, SSOT 외 운영 확장)

### 맥락

SSOT 측 정의:
- 비밀번호 찾기(F-104)는 정의되어 있다.
- **아이디(이메일) 찾기는 정의되어 있지 않다.**

사용자 리서치 결과:
- 한국 사용자는 가입 이메일을 잊는 빈도가 매우 높다(특히 OAuth 가입 후 시간이 지난 경우).
- 본 서비스는 SMS 인증 기반 OTP 인프라를 이미 보유(Story 4.1) → 추가 비용 없이 SMS 기반 ID 찾기 구현 가능.

### 결정

**SMS 인증 기반 이메일 찾기 기능을 신설**한다(SSOT 외 운영 확장 — 클라이언트 동의).

- 엔드포인트: `POST /api/v1/auth/lookup-id`
- 입력: 가입 시 등록한 휴대폰 번호 + SMS OTP 코드
- 출력: 마스킹된 이메일(예: `da***@gmail.com`) 화면 표시 — 평문 노출 금지(PIPA 준수)
- OAuth 가입 사용자 식별:
  - **현 구현 (2026-04-24 기준)**: `users.signup_method` 컬럼은 `User` ORM 모델(`api/src/models/user.py`)에 **미정의**. 식별은 `oauth_identity` 테이블(`api/alembic/versions/0004_oauth_identity.py`) 조인으로 표현 (`auth_service.py`·`schemas/auth.py` 참조).
  - **향후 정식화**: Story 1.6 마이그레이션 후속 또는 별도 리팩토링 스토리에서 `users.signup_method` 컬럼을 ORM에 추가하면 4값(`email`·`kakao`·`google`·`naver`) ENUM 일원화. 현 시점은 조인 기반.
- **Rate limit (브루트포스·전화번호 사전 공격 방지 필수)**:
  - Redis DB2(`REDIS_DB_RATE_LIMIT`) 기반 limiter 적용
  - 동일 휴대폰 번호: 5분에 3회 (OTP 발송 단계)
  - 동일 IP: 1분에 10회 (전화번호 사전 공격 방지)
  - 초과 시 429 `RATE_LIMITED` 응답
  - PIPA 준수: 마스킹은 노출은 막지만 "해당 번호로 가입된 계정 존재 여부"는 응답 분기(200 vs 404)로 유출 가능 → rate limit으로 가입자 사전 매칭 공격 차단

### 근거

- 사용자 마찰 감소: 비밀번호 찾기와 대칭되는 ID 찾기로 로그인 불능 사용자 구제.
- 인프라 재사용: 기존 SMS OTP 어댑터(`api/src/integrations/messaging/`) 재활용으로 신규 인프라 비용 0.
- PIPA(개인정보 보호법) 준수: 마스킹 처리로 PII 누설 방지.

### 영향받는 산출물

| 분류 | 항목 |
|---|---|
| PRD FR | FR10(SMS 기반 이메일 찾기) |
| Epic/Story | Epic 1 Story 1.5(`/api/v1/auth/lookup-id` 구현), Story 1.6 AC-11(`signup_method` 4값 확장) |
| 데이터베이스 | `oauth_identity` 테이블(`api/alembic/versions/0004_oauth_identity.py`) — 현 시점 OAuth 가입자 식별 경로. `users.signup_method` ORM 컬럼 추가는 별도 리팩토링 (TBD) |
| Rate Limit | `REDIS_DB_RATE_LIMIT`(Redis DB2) — `lookup_id_phone:{phone}` (5분 3회) + `lookup_id_ip:{ip}` (1분 10회) |
| 프론트엔드 | `web/src/features/auth/FindIdPopup.tsx`(존재 확인) — 마스킹 표시 UX |
| 백엔드 | `api/src/routers/auth.py`(존재 확인) — `lookup-id` 엔드포인트 |
| 변경 관리 절차 | 기능명세서 §9 변경 관리 절차에 등재 — 본 ADR이 그 등재 매개체 |

### 날짜·승인자

2026-04-22 · Hyung woo ↔ 클라이언트 · ADR 등재일 2026-04-24

---

## 편차 #4 — kill-switch(비상 정지 스위치) 범위 교정(이원 모드)

### 상태

**Accepted** (2026-04-22 클라이언트 재확인으로 PRD FR56 초판 오류 교정)

### 맥락

SSOT 측 정의(기능명세서 A-101 p.27 + A-502 p.29 + 협의서 #B-05):
- **평상시 자동 무료 차단** + **비상시 수동 전체 정지** + **경고·수동 정지 양립**의 3가지 정책이 한 번에 명세됨.
- 자동 모드: 월 예산 80% / 95% 알림톡 경고 → 100% 도달 시 무료 사용자 질의만 자동 차단(유료 구독자는 정상 동작).
- 수동 모드: 관리자가 비상시 전체 정지(유료·무료 모두 차단).
- 수동 정지 시 유료 구독자에게는 정지 기간만큼 구독 기간을 자동 연장한다(이용약관 명시).

PRD FR56 **초판 오류**:
- 초판에 "유료 질의 전역 차단"으로 단일 모드처럼 잘못 번역되었다.
- 2026-04-22 클라이언트 재확인 미팅에서 SSOT가 이원 모드임을 재확인 → ADR로 교정.

### 결정

**`killswitch_states.mode` enum으로 이원 모드를 관리**한다.

| 모드 | 트리거 | 차단 범위 | 활성자 |
|---|---|---|---|
| `auto_free_only` | 월 예산 100% 도달 시 자동 ON | 무료 사용자 질의만 차단(유료 정상) | 시스템(`activated_by_admin_id=NULL`) |
| `manual_total` | 관리자 수동 발동 | 유료·무료 모두 차단 | 관리자(`activated_by_admin_id` 기록) |

추가 정책:
- **3단계 자동 알림톡 경고**: 80% / 95% / 100% 시점에 관리자 휴대폰으로 알림톡 발송(이메일 0건 원칙 준수 — `project_email_zero_policy.md`).
- **두 모드 병존 가능**: `uq_killswitch_active_mode` partial UNIQUE(`mode`, WHERE `deactivated_at IS NULL`)로 동일 모드 중복 활성만 방지하고, 서로 다른 모드는 동시 활성 가능.
- **OR 평가**: 질의 차단 판정은 "둘 중 하나라도 ON이면 해당 모드 정책 적용"으로 OR 평가하며 `manual_total` 우선(전체 차단이 무료만 차단의 상위 집합).
- **이용약관 조항**: "수동 kill-switch 발동 시 유료 구독 기간을 정지 기간만큼 자동 연장"(`docs/legal/terms.md` — Story 9.2 범위에서 작성).

### 근거

- SSOT 충실성: 클라이언트 기능명세서 원문(A-101 + A-502 + 협의서 #B-05)을 정확히 반영.
- 운영 안전망: 자동 모드(예산 보호) + 수동 모드(시스템·법적 비상)의 양립으로 관리자 의사결정 지점이 명확.
- 이메일 0건 원칙(`project_email_zero_policy.md`): 80/95% 경고는 모두 알림톡(`notification_service.send_alimtalk` 카테고리 `system`)으로 발송. PRD FR56 초판의 "이메일 80%·95%" 표현은 본 ADR에서 알림톡으로 교정한다.

### 영향받는 산출물

| 분류 | 항목 |
|---|---|
| PRD FR | FR56(예산 경고 + kill-switch) — **본 ADR이 정정 SSOT** |
| Epic/Story | Epic 9 Story 9.2(`killswitch_states`·`KillSwitchPanel`·`/admin/finance/killswitch`), Epic 5 Story 5.2(예산 경고 알림톡 발송 로직), Epic 9 Story 9.4(본 ADR) |
| 데이터베이스 | `killswitch_states`(Story 9.2 마이그레이션), `budget_thresholds`(Story 5.2 마이그레이션) — 둘 다 현 시점 미생성(Wave 4·9 backlog) |
| 백엔드 | `api/src/services/killswitch_service.py`·`api/src/services/budget_service.py`·`api/src/workers/budget_tasks.py`·`api/src/routers/admin/{killswitch,finance}.py` — TBD(Story 5.2·9.2) |
| 프론트엔드 | `web/src/features/admin-finance/KillSwitchPanel.tsx`·`BudgetGauge.tsx` — TBD(Story 5.2·9.2) |
| 알림톡 템플릿 | `api/src/integrations/messaging/templates.py`에 추가 — Story 단일 소유 명확화: |
| ↳ Story 5.2 (예산 경고 발송 로직 + 트리거 워커) | `admin.budget_warning_80`·`admin.budget_warning_95`·`admin.budget_hard_cap_reached` 템플릿 등록 + 80/95/100% 임계 도달 감지 워커 |
| ↳ Story 9.2 (KillSwitchPanel UI/State + manual_total) | `admin.killswitch_manual_activated`·`admin.killswitch_manual_deactivated` 템플릿 등록 + `killswitch_states` 테이블·관리자 UI |
| ↳ 양쪽 의존 (HOLD-MSG) | 5.2의 발송 로직은 stub 어댑터로도 동작하므로 Wave 4에서 착수 가능. 9.2는 HOLD-MSG 해제 후 실 어댑터로 운영 검증 |
| 약관 | `docs/legal/terms.md`(수동 kill-switch 시 유료 구독 기간 자동 연장 조항) — Story 9.2 범위 |
| PRD 본문 | `_bmad-output/planning-artifacts/prd.md:629` — Post-MVP 문서 유지보수 시 본 ADR 결정으로 본문 교정 예정 |

### 날짜·승인자

2026-04-22 · Hyung woo ↔ 클라이언트 · ADR 등재일 2026-04-24

---

## 편차 #5 — 환불 정책 부분환불 전환(자가 환불 폼 폐지 + 청약철회 + 관리자 자유 금액 입력)

### 상태

**Accepted** (2026-05-12 클라이언트 확정)

### 맥락

SSOT 측 정의(F-207 + 협의서 #B-03 + PRD FR19 초판):
- 사용자가 마이페이지에서 **환불 요청 폼**을 제출 → 관리자 승인 → 환불 처리
- 자동 환불 조건: 결제 후 7일 이내 AND 해당 구독 기간 동안 질문 0건
- 조건 미충족 시 "관리자 수동 검토" 경로로 전환 (전액 환불 가정)

운영상 검토 (2026-05-12 사용자 확인):
- **구독형 서비스는 본질적으로 "환불"이 아닌 "구독 취소"가 기본**이다. 7일이 지나면 다음 결제일 차단이 자연스러우며, 별도 환불 요청 폼이 존재할 필요가 없다.
- 한국 전자상거래법은 청약철회(7일 이내 전액 환불)만 강제하므로, 7일 이후의 사용자 변심 환불은 법적 의무가 아니다.
- 운영 환불(중복결제·시스템 장애)·특별 중도해지(클라이언트 호의)는 항상 발생하며, 이때 **부분 환불(일할 계산)** 수요가 있다.
- 토스 페이먼츠 자동결제(빌링) API의 `cancelAmount` 파라미터로 전액·부분 환불을 모두 지원하며, 동일 결제 건에 대한 다회 부분환불도 가능함을 확인 (`docs.tosspayments.com/guides/v2/cancel-payment`).

### 결정

환불 시스템을 **사용자 자가 환불 요청 경로 폐지 + 청약철회 자동 환불 + 관리자 자유 금액 입력 환불**의 3단 구조로 재편한다.

**(a) 일반 구독 취소 (7일 이후 또는 질문 1건 이상)**
- 사용자는 마이페이지에서 "구독 취소" 버튼만 누른다. 환불은 동반되지 않는다.
- 현재 결제 주기 종료일까지 유료 기능 유지 → 다음 결제일에 자동결제 차단.

**(b) 청약철회 (7일 이내 & 질문 0건)**
- 사용자는 같은 "구독 취소" 동선 안에서 "지금 즉시 해지 + 전액 환불"을 선택할 수 있다. 별도 환불 요청 폼은 없다.
- 시스템이 자동으로 조건을 검증하고 토스 `cancelAmount`(생략 = 전액)로 즉시 환불 호출. 사용자에게 알림톡 발송.

**(c) 운영 환불 (관리자 수동, 전액·부분 자유)**
- 관리자는 결제 건당 **환불 금액을 직접 입력**한다. 화면에는 다음이 표기되나 강제되지 않는다:
  - 결제 금액
  - 환불 가능 잔액 (= 결제 원금 − 기존 부분환불 누적)
  - **참고 계산값**: 전액 환불 / 일할 환불 권장액 / 청약철회 적용 가능 여부
- **일할 환불 권장액 공식**: `결제 금액 × (남은 일수 ÷ 총 구독 일수)`, 원 단위 내림(소비자에게 불리하지 않게).
- **가드레일**:
  1. 입력 금액 > 환불 가능 잔액 → 입력 단계에서 차단, 버튼 비활성.
  2. 입력 금액 ≤ 0 → 버튼 비활성.
  3. 환불 버튼 클릭 시 **금액 재확인 모달(2단계 확인)** 통과 후 토스 호출.
  4. 토스 호출 실패 시 "실패" 상태로 환불 기록 저장 + 사용자 알림톡 미발송.
- **사유 분류 필수**: 고객 불만 · 중복결제 · 시스템 장애 · 특별 중도해지 · 기타. 자유 메모도 함께 기록.
- 모든 환불 기록은 `audit_logs`에 액션 코드 `admin.refund.processed`로 영구 보존.

### 근거

- **법적 적합성**: 청약철회권(7일 이내 전액 환불)은 자동 경로로 보장하면서 사용자가 별도 폼을 채울 필요가 없어 사용자 마찰 감소.
- **운영 유연성**: 관리자가 사유·금액을 그때그때 판단하므로 케이스 분기 코드를 시스템에 박지 않아도 됨(특별 중도해지, 호의 환불, 일할 계산 모두 동일 UI에서 처리).
- **토스 API 적합**: `cancelAmount` 한 줄로 시스템 단순. 다회 부분환불도 `Payment.cancels` 배열로 누적 관리 가능.
- **분쟁 최소화**: "일할 계산" 공식이 PRD에 명시되어 있으나 강제하지 않음 → 관리자가 클라이언트 정책에 맞춰 재량 조정 가능.

### 영향받는 산출물

| 분류 | 항목 |
|---|---|
| PRD FR | FR17(해지=환불 비동반 명시), FR19(환불 정책 전면 재작성 — 청약철회 + 운영 환불 이원), FR29(환불 알림톡에 금액·사유 포함), FR55(결제 기록에 부분환불 누적·잔액·사유 표시) |
| Epic/Story | Epic 3 Story 3.6(환불 — 사용자 자가 환불 폼 폐지, 청약철회 자동 환불 경로로 재설계), Epic 4 Story 4.3·4.4(마이페이지 — "구독 취소" 단일 버튼, 청약철회 조건 충족 시만 "전액 환불 동반" 옵션 노출), Epic 9 Story 9.3(관리자 수동 환불 — 금액 입력 + 참고 계산값 표기 + 2단계 확인 + 잔액 가드) |
| 데이터베이스 | `refunds` 테이블 — `cancel_amount`(부분환불 금액, NOT NULL), `original_payment_amount`(스냅샷), `prorated_suggestion`(권장액 스냅샷, NULLABLE), `reason_category`(ENUM), `memo`(TEXT), `refund_sequence`(동일 결제 건 내 다회 부분환불 시퀀스). 기존 단일 "전액 환불" 가정 컬럼이 있다면 마이그레이션 필요 |
| 백엔드 | `api/src/services/refund_service.py` — 청약철회 조건 자동 검증 함수 + 잔액 검증 함수 + 일할 계산 함수 + 토스 `cancelAmount` 호출. `api/src/integrations/payment/toss_adapter.py` — `cancelAmount` 파라미터 지원 확장 |
| 프론트엔드 | `web/src/features/account/SubscriptionCancel.tsx`(마이페이지 구독 취소 UI), `web/src/features/admin-finance/RefundDialog.tsx`(관리자 환불 금액 입력 + 참고 계산값 + 2단계 확인 모달) |
| 알림톡 템플릿 | `docs/ALIMTALK_TEMPLATES.md` + `api/src/integrations/messaging/templates.py` — `user.subscription_cancelled`(구독 취소), `user.refund_completed`(환불 완료, 금액·사유 변수 포함), `user.refund_failed`(환불 실패) 신규 등록 |
| 약관 | `docs/legal/terms.md` — 환불 정책 절 재작성(① 청약철회 ② 일반 구독 취소 ③ 운영 환불의 3단 명시) |
| 변경 관리 절차 | 기능명세서 §9 변경 관리 절차에 등재 — 본 ADR이 그 등재 매개체 |

### 날짜·승인자

2026-05-12 · Hyung woo(개발사) ↔ 클라이언트 합의 · ADR 등재일 2026-05-12

---

## 편차 #6 — 다중 관리자 RBAC 도입(단일 관리자 → 4등급 권한 체계)

### 상태

**Accepted** (2026-05-26 클라이언트 확정)

### 맥락

SSOT 측 정의(기능명세서 §관리자 + PRD FR33~FR57 초판):
- 관리자는 **단일 계정**으로 운영한다(개발자 시드 `btmdesign@naver.com` 1개).
- 등급·페이지별 권한·승인 워크플로·관리자 활동 로그 등 RBAC 요소는 정의되어 있지 않다.
- 마스터 식별은 코드 하드코딩(`api/src/services/admin_board_service.py:BTMDESIGN_EMAIL` 상수)으로 구현되어 있다.

운영상 검토(2026-05-26 클라이언트 미팅):
- **휴가·이양·업무 분담 불능**: 단일 계정 운영 시 개발자 부재 기간(휴가·이양·이직) 동안 관리자 액션이 0건이 된다.
- **운영 책임 단일 의존**: 모든 관리자 액션이 한 사람에게 귀속 — 책임 분담·이중 점검·역할 분리(SoD, Separation of Duties)가 불가.
- **외주 운영 시 제약**: 클라이언트 측 운영 인력(고객 응대·콘텐츠 발행)에게 일부 페이지만 위임하고 싶어도 전체 권한이 묶여 있어 불가.
- **마스터 하드코딩 부담**: `BTMDESIGN_EMAIL` 상수를 코드에 박아두는 방식은 이메일 변경 시 배포가 필요하며 이양 시 git diff에 노출된다.

### 결정

관리자 시스템을 **단일 계정 → 다중 관리자 + 4등급 RBAC**로 확장한다. PRD에 **§10 Admin Account & RBAC**(FR58~FR63) 섹션을 신설하고, Epic 10을 추가하여 5개 Story로 분해한다.

**(a) 등급 체계 — 4종 고정**

| 등급 코드 | 한글명 | 권한 범위 | 단일성 |
|---|---|---|---|
| `master` | 마스터 | 모든 관리자 기능 + 운영 관리자 자체의 승인/차단/삭제/등급 변경 + 페이지 권한 매트릭스 편집 | **DB partial UNIQUE로 1개만 허용** |
| `operator` | 운영 관리자 | 마스터 전용 기능 제외한 모든 관리자 페이지 접근 | 다수 가능 |
| `sub_operator` | 부운영자 | 운영 관리자가 부여한 페이지만 접근(기본 권한 0) | 다수 가능 |
| `pending` | 승인대기 | 모든 관리자 페이지 접근 불가(로그인 자체 차단, 세션 미발급) | 다수 가능 |

**(b) 가입 워크플로**

- 가입 경로: **`/admin/signup`**(독립 경로, 일반 사용자 가입 폼과 완전 분리, 일반 사이트 어디에서도 링크 노출 없음 — `/admin/login` 페이지 내부에서만 진입 가능)
- 가입 시 자동으로 `admin_grade='pending'` 부여
- 가입 알림은 마스터·운영 관리자 휴대폰으로 알림톡 발송(이메일 0건 원칙 — `project_email_zero_policy.md`)
- 승인 단계에서 `pending → sub_operator`(기본) 또는 `pending → operator`(마스터만 가능)

**(c) 등급 부여 규칙 — "자기 등급 이상은 못 줌"**

- `operator`는 다른 `operator`·`master`를 만들거나 그들에게 영향을 줄 수 없음 → `sub_operator`·`pending` 대상만 관리
- `master`는 모든 등급을 부여 가능(단, master 부여는 단일성 제약으로 불가)
- 권한 검증은 백엔드 서비스 레이어(`admin_account_service.py`)에서 강제 + 프론트 UI에서도 액션 버튼 사전 비활성

**(d) 페이지별 권한 매트릭스 — `sub_operator` 한정**

- 페이지 단위: 관리자 사이드바의 1차 라우트 8종(`/admin/dashboard`·`/admin/users`·`/admin/finance`·`/admin/rag`·`/admin/content`·`/admin/anomaly`·`/admin/support`·`/admin/admins`)
- 신규 테이블 `admin_page_permissions(admin_user_id BIGINT FK, page_route VARCHAR(64), allowed BOOL, granted_by_admin_id BIGINT FK, granted_at TIMESTAMPTZ)` — 행 단위 ON/OFF
- `master`·`operator`는 본 매트릭스 적용 대상 아님(항상 모든 페이지 접근)
- `/admin/admins`·`/admin/admins/permissions` 자체는 매트릭스 적용 대상이 아니며 `master`·`operator`만 접근 가능

**(e) 관리자 활동 로그 — 기존 `audit_logs` 재사용**

- 신규 액션 코드: `admin.account.{approved,blocked,unblocked,deleted,grade_changed,permission_changed}` + `admin.master.protection_triggered`
- 뷰 페이지: **`/admin/admins/logs`** — 관리자별·기간별·액션 코드별 필터
- `operator`는 자기 자신 + `sub_operator`의 활동만 조회 / `master`는 전체 조회

**(f) 마스터 무결성 보장**

- DB partial UNIQUE: `uq_admin_grade_master ON users(admin_grade) WHERE admin_grade='master' AND withdrawn_at IS NULL`
- API 레벨 403: master 대상 차단·삭제·등급 변경 요청 거부
- UI 액션 버튼 비활성 + 비정상 시도는 `admin.master.protection_triggered`로 별도 기록
- 마스터 이양·복수 등록 정책은 본 MVP 범위 외(Post-MVP 클라이언트 협의)

**(g) 기존 단일 관리자 마이그레이션**

- 마이그레이션 시점에 `users` 테이블에서 `role='admin' AND withdrawn_at IS NULL`인 모든 행을 다음 규칙으로 백필:
  - `email = 'btmdesign@naver.com'` → `admin_grade = 'master'`
  - 그 외 → `admin_grade = 'operator'`(현재 시드된 관리자가 마스터 단 1개뿐이라 사실상 master 백필만 적용됨)
- `BTMDESIGN_EMAIL` 상수는 마이그레이션 후 **deprecation 주석**으로 표시되며 후속 Story에서 일괄 제거(`admin_grade='master'` 컬럼 조회로 대체)

### 근거

- **운영 안전망**: 단일 의존 제거 → 휴가·이양·업무 분담 가능. SoD(Separation of Duties) 도입으로 이중 점검 경로 확보.
- **유연한 권한 위임**: 페이지별 매트릭스로 고객 응대·콘텐츠 발행·결제 운영 등을 부운영자에게 부분 위임 가능. 외주 운영 인력 도입 시에도 보안 부담 최소화.
- **하드코딩 제거**: `BTMDESIGN_EMAIL` 상수를 DB 컬럼으로 이관 → 마스터 이양·이메일 변경 시 코드 배포 불필요. ENUM 1개 + partial UNIQUE 1개로 단순 모델 유지.
- **기존 인프라 재사용**: 가입 SMS OTP·관리자 쿠키 분리(`denvia_admin_session`, path `/api/v1/admin`)·`audit_logs`·관리자 알림톡 발송 경로는 모두 기존 인프라 그대로 활용. 신규 컬럼 2개 + 신규 테이블 1개로 surface 최소화.
- **이메일 0건 원칙 준수**: 가입·승인·차단 알림은 모두 알림톡으로 발송(`project_email_zero_policy.md`).

### 영향받는 산출물

| 분류 | 항목 |
|---|---|
| PRD FR | **신규 FR58·FR59·FR60·FR61·FR62·FR63** (§10 Admin Account & RBAC) |
| Epic/Story | **신규 Epic 10**: Story 10.1(DB 스키마+마이그레이션), 10.2(가입+승인대기), 10.3(관리자 관리 페이지 CRUD), 10.4(활동 로그 뷰), 10.5(페이지별 권한 매트릭스 UI) |
| 데이터베이스 | `users.admin_grade` ENUM 컬럼 추가('master'/'operator'/'sub_operator'/'pending'/NULL — non-admin은 NULL) + partial UNIQUE `uq_admin_grade_master` + `users.admin_blocked_until` + `users.admin_block_reason` + 신규 테이블 `admin_page_permissions(id, admin_user_id FK users.id, page_route VARCHAR(64), allowed BOOL, granted_by_admin_id FK users.id, granted_at TIMESTAMPTZ)` + UNIQUE(admin_user_id, page_route) |
| 백엔드 | `api/src/services/admin_account_service.py`(신규 — 등급 검증·승인·차단·삭제·권한 매트릭스) · `api/src/routers/admin/accounts.py`(신규 — 관리자 관리 CRUD) · `api/src/routers/admin/permissions.py`(신규 — 페이지 권한 매트릭스) · `api/src/deps/auth.py`(`get_current_admin` 확장 → 등급·페이지 권한 검증 추가) · `api/src/routers/admin/auth.py`(signup 엔드포인트 추가 + pending 거절) · `api/src/services/admin_board_service.py`(`BTMDESIGN_EMAIL` 상수 deprecation 마킹) |
| 프론트엔드 | `web/src/features/admin-accounts/`(신규 슬라이스 — AdminListTable, GradeChangeDialog, AdminPermissionMatrix, AdminLogsTimeline, AdminSignupForm) · `web/src/app/admin/signup/page.tsx`(신규 라우트) · `web/src/app/admin/admins/{page,permissions,logs}/page.tsx`(신규 라우트) · 관리자 사이드바에 "관리자 관리" 1차 항목 추가 |
| 알림톡 템플릿 | `api/src/integrations/messaging/templates.py`에 추가 — `admin.account.signup_request`(가입 신청 → 마스터·운영 관리자에게), `admin.account.approved`(승인 완료 → 신규 관리자에게), `admin.account.blocked`(차단 → 대상 관리자에게), `admin.account.deleted`(삭제 → 대상 관리자에게). `docs/ALIMTALK_TEMPLATES.md` SSOT 동기화 |
| 약관·내부 문서 | `docs/legal/terms.md`는 외부 사용자 약관이므로 영향 없음. `docs/SECURITY.md`에 관리자 RBAC 절 추가(역할 정의·권한 행렬·이양 절차) |
| 코드 하드코딩 제거 | `BTMDESIGN_EMAIL` 상수 → `admin_grade='master'` DB 조회로 대체. Story 10.1 마이그레이션 직후 Story 10.3 진입 전 일괄 deprecation |
| 변경 관리 절차 | 기능명세서 §9 변경 관리 절차에 등재 — 본 ADR이 그 등재 매개체 |

### 날짜·승인자

2026-05-26 · Hyung woo(개발사) ↔ 클라이언트 합의 · ADR 등재일 2026-05-26

---

## 검증 이력

| 날짜 | 검증자 | 결과 | 조치 |
|---|---|---|---|
| 2026-04-24 | Hyung woo | OK — **다중 결정 ADR 패턴**(`docs/adr/README.md` 작성 규칙 참조)에 따라 편차 4건이 각각 H2(`## 편차 #N`) + 그 안에 6개 H3 섹션(상태·맥락·결정·근거·영향받는 산출물·날짜·승인자) 엄수 확인. PRD FR10/FR11/FR28/FR56 인용 라인(`prd.md:559`·`:586`·`:629`) 실재 검증 완료. `users.segment`·`users.years_of_experience` 컬럼 실재(`api/src/models/user.py:22-23`) 검증. `web/src/features/auth/SegmentSelect.tsx`·`FindIdPopup.tsx` 실재 검증. | — |
| 2026-04-24 | Hyung woo (code-review D1 적용) | OK — README "다중 결정 ADR 패턴" 신설로 본 ADR 구조 정합성 공식 확인. 자체 검증 이력 문구도 패턴 명시로 정정. | — |
| 2026-04-24 | claude-opus-4-7 (code-review 후속 6건 patch 적용) | OK — 메타 헤더 Story 번호 9건 정렬(`1.3·1.5·1.6·4.3·5.2·6.2·6.4·9.2·9.4` 일치), 편차 #2 기존 데이터 마이그레이션 SQL + alembic data migration 추가, 편차 #3 `signup_method` ORM 미정의 정정(oauth_identity 조인 명시) + Rate Limit(Redis DB2) 정책 추가, 편차 #4 알림톡 템플릿 Story 5.2(발송 로직)·9.2(KillSwitchPanel UI/State) 단일 소유 명확화 적용 완료. README 인덱스 표 Story 번호도 동일 정렬. | — |
| 2026-05-12 | claude-opus-4-7 (편차 #5 추가) | OK — 편차 #5(환불 정책 부분환불 전환) 6개 H3 섹션 엄수 등재. PRD FR17/FR19/FR29/FR55 본문 동시 갱신. 메타 헤더 Story 번호 확장(`3.3·3.4·3.6·4.4·9.3` 추가). README 인덱스 표 정렬은 후속 작업으로 분리(`docs/adr/README.md` 별도 patch 필요). | README 인덱스 표 정렬 TBD |
| 2026-05-13 | claude-opus-4-7 (편차 #5 Phase 4 cleanup) | OK — 편차 #5 v1.0 자가 환불 잔재(폼·관리자 승인 큐·`manual_refund_queue` 참조 코드) dead code 제거 완료. **Step 1**(백엔드, commit `970de94`): ORM `manual_refund_queue.py`·`routers/admin/refunds.py`·`services/admin_refund_service.py`·`schemas/admin/refunds.py`·테스트 일괄 삭제. main 라우터 mount/finance ORM lookup/admin support count 호출도 해제. **Step 2**(프론트, commit `4112da1`): `RefundRequestPopup`·`useRequestRefund`·`billing.requestRefund`·admin-support 환불 큐 패널(`RefundsTabPanel`/`RefundReviewDrawer`/`RefundQueueTable`/`RefundActionConfirmDialog`/`SupportTabsNav`/`api/refunds.ts`)·admin-finance refund 큐 링크·`PaymentEventDetail.manual_refund_queue_*` 필드 삭제. vitest 35/35 PASS. **Step 3**(문서): `_bmad-output/planning-artifacts/epics.md`(Story 3.6·4.4·9.3 v1.0 ACs를 OBSOLETE 마킹), `_bmad-output/implementation-artifacts/3-6-refund-request.md`(Phase 4 Patch-T2·T8 status `[x]` flip + Step 1~4 진행 노트), `docs/RUNBOOK_INCIDENT.md` 시나리오 ① 결제 장애 조치 단계(`manual_refund_queue INSERT` → v1.1 운영 환불 동선 / Story 9.1 RefundDialog). **Step 4 잔여**: Patch-T1(0017 drop 마이그) — 코드 의존성 0이므로 단독 안전. 메모리 `project_refund_policy` 9.3 → 9.1 stale 참조 1건 정정 동반. | Patch-T1(0017 drop 마이그) — Step 4로 별도 PR |
| 2026-05-14 | claude-opus-4-7 (편차 #5 후속 — `payment_events.refund_kind` 컬럼 승격) | OK — 편차 #5 환불 정책 v1.1의 분류 메타를 JSONB 인라인에서 전용 ENUM 컬럼으로 승격. 마이그 `0035_payment_events_refund_kind`: `refund_kind_enum`('manual_full'/'manual_partial'/'cooling_off') + `payment_events.refund_kind` NULL 허용 컬럼 + 부분 인덱스 `idx_payment_events_refund_kind WHERE refund_kind IS NOT NULL` + 기존 행 백필(JSONB→컬럼). ORM `payment_event.PaymentEvent.refund_kind` 매핑 추가. 서비스 수정 4지점: `admin_payment_service.create_refund` refund_success/refund_denied INSERT 2지점 + `billing_service._execute_cooling_off_refund` refund_success/refund_denied INSERT 2지점 — JSONB 인라인 `raw_response_json.refund_kind`는 한 사이클 호환 유지 후 후속 클린업 마이그에서 제거 검토. 테스트 보강 6 케이스(unit `test_admin_payment_service_v1_1` 4 + `test_billing_service_3_6_v1_1` 2). dev DB \dt 26 tables / alembic_version=0035_payment_events_refund_kind / admin login 200 / scoped 72 PASS(unit 29 + integration 43). 코드 리뷰 티어: **라이트** — 컬럼 추가만으로 surface 좁고 NULL 허용 + 백필 안전(enum 외 값 SKIP) + 신규 보안 surface 0 + 금전 이동 0(분류 메타만) + 권한 변경 0. | JSONB 인라인 `raw_response_json.refund_kind` 클린업 마이그 — 후속 |
| 2026-05-26 | claude-opus-4-7 (편차 #6 등재 — 다중 관리자 RBAC) | OK — 편차 #6(다중 관리자 + 4등급 RBAC) 6개 H3 섹션 엄수 등재. ADR 헤더 v1.1→v1.2 / Story 번호 확장(10.1·10.2·10.3·10.4·10.5 추가). PRD 본문 §10 Admin Account & RBAC 섹션 신설(FR58~FR63 6개 신규). PRD 헤더 FR 카운트 57→63. README 인덱스 표 정렬 + sprint-status.yaml backlog 등록 + epics.md Epic 10 추가는 후속 분리 작업. **본 ADR 등재 시점 코드 변경 0** — DB 마이그·라우터·UI는 Story 10.1~10.5 진입 시 순차 구현. | epics.md Epic 10 / sprint-status.yaml Epic 10 backlog / README 인덱스 표 정렬 — 후속 |
| 2026-05-27 | claude-opus-4-7 (편차 #6 Story 10.3 진입 — BTMDESIGN_EMAIL 하드코딩 일괄 제거) | OK — Story 10.3(관리자 관리 페이지 CRUD + 등급 제약)에서 마스터 식별을 `users.admin_grade='master'` DB 컬럼 기준으로 일괄 교체. **변경 지점 4**: ① `services/admin_board_service.is_btmdesign(user)` 내부 판정을 이메일 비교 → `user.admin_grade=='master'` 로 변경(함수 시그니처는 호출 측 호환을 위해 유지) · ② `routers/admin/auth._grade_label_for(email)` 함수 폐기 → `services/admin_account_service.grade_label_for_user(user)` 신규 + 3개 호출 지점(`admin_login`/`admin_me`/`admin_get_profile`/`admin_update_profile`) 교체 · ③ `integrations/messaging/admin_recipient.resolve_admin_target` 마스터 조회를 `email==BTMDESIGN_EMAIL` → `admin_grade=='master' AND withdrawn_at IS NULL` 로 변경 · ④ `BTMDESIGN_EMAIL` 상수는 `admin_board_service` 에 deprecated alias 로 1 사이클 유지(후속 클린업 마이그에서 제거 검토). 신규 라우터 `routers/admin/accounts.py` + 신규 서비스 `services/admin_account_service.py` + Celery `expire_blocks` 에 admin 변형 핸들러 통합. **알림톡 4종(admin.account.{approved,blocked,unblocked,deleted})은 같은 날 일시 추가됐다가 즉시 제거** — 운영자가 `/admin/admins` 페이지에서 대상자 휴대폰을 직접 보고 별도 채널로 안내, 알림톡 surface 추가 보류. 자동 만료 알림 발송도 없음. | `BTMDESIGN_EMAIL` 상수 완전 삭제 — 후속 클린업 마이그(Story 10.5 이후) |
| 2026-05-27 | claude-opus-4-7 (편차 #6 Story 10.4 dev-story — 활동 로그 SSOT 편차 2건 발견) | OK — Story 10.4(/admin/admins/logs 활동 로그) dev-story 진행 중 epics.md §10.4 와 실제 코드 간 SSOT 편차 2건 식별·조정. **편차 A**: epics.md §10.4 "신규 인덱스 1개 추가 권장 — `idx_audit_logs_actor_created`" 명시 → 실제로는 `0005_audit_logs.py:48-52` 에 동일 정의(`actor_user_id`, `created_at DESC`)가 **이미 존재**. 본 Story 신규 인덱스 추가 0건(중복 생성 시 alembic 에러). **편차 B**: epics.md §10.4 "시스템 자동 액션은 `actor_user_id IS NULL` 로 기록" 가정 → 실제로는 `audit_logs.actor_user_id` NOT NULL + FK ON DELETE RESTRICT 제약(0005). 시스템 액션(Celery `expire_blocks`)도 `_resolve_system_actor_id` 가 결정한 **첫 admin user id** 로 INSERT 됨(`workers/anomaly_tasks.py:44`). 본 Story 의 `actor_id=system` 옵션은 action 코드 패턴(`user.block_auto_expired` / `admin.account.unblocked`) + actor_user_id 가 첫 admin id 인 조합으로 식별 — 정확성 한계 있음(첫 admin 이 수동 unblock 한 로그도 "시스템" 으로 분류될 수 있음). **신규 코드 / 마이그 0건 — 순수 READ 페이지**: `services/admin_logs_service.py` 신규(list_logs/get_log_diff/export_logs_xlsx + _redact_diff 15종 키 화이트리스트 + _assert_log_visible_to 가드) · `schemas/admin/log.py` 신규(3 응답) · `routers/admin/accounts.py` 3 endpoint append(GET /logs · GET /logs/{id}/diff · GET /logs/export.xlsx). 프론트 `web/src/features/admin-logs/` 신규 슬라이스(api.ts + action-groups.ts) + `web/src/app/admin/admins/logs/` 신규 페이지(page.tsx + LogRow.tsx + page.module.css) + AdminSidebar children 신설("관리자 목록" + "활동 로그"). 권한 분기: master 전체 + actor_id=system 옵션 / operator 본인+활성 sub_operator 만 / 다른 actor 403 ADMIN_LOG_FORBIDDEN_ACTOR. 테스트 32 PASS(unit redact 9 + visibility 12 + integration 11). 코드 리뷰 티어: **라이트** — DDL 0 / 신규 INSERT 0 / 신규 인덱스 0 / RAG·금전 영향 0 / 권한 분기 1 헬퍼 응집 / READ 전용. | `audit_logs.actor_kind ENUM('user','admin','system')` 컬럼 신설 — 별도 백로그(Story 10.5 done 이후 협의) |
