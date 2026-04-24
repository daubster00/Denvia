# ONBOARDING — Denvia 관리자 첫 사용 가이드

> **최종 수정일:** 2026-04-24
> **작성자:** Hyung woo
> **승인자:** (인수자 검토 시 기입)
> **버전:** v1.0
> **관련 FR/Story:** Journey 4(10분 내 운영 자치권 체감) / Story 9.4

본 문서는 인수자가 Denvia를 처음 인계받았을 때 **10분 내** 핵심 관리자 작업 4종을 익혀 운영 자치권을 확보하기 위한 단계별 가이드다.

> **목표 검증 흐름**: 본 4단계를 외부 조력 없이 순서대로 완료할 수 있어야 한다(Journey 4 검증 기준).

> ⚠️ **현 시점 검증 가능 범위 안내 (2026-04-24 기준)**:
> 본 4단계 흐름은 다음 스토리들이 모두 완료된 후 정식 검증된다:
> - **Step 1 (관리자 로그인)**: Story 5.1 (관리자 셸 라우팅) 완료 후 `/admin/dashboard` 진입 가능. 현재는 단계별 dry-run만 가능.
> - **Step 2 (TXT 업로드)**: Story 8.1 (TXT 업로드 + 포맷 검증) 완료 후.
> - **Step 3 (재빌드)**: Story 8.3 (FAISS 스왑) 완료 후.
> - **Step 4 (공지 발송)**: Story 7.1 (공지 RichTextEditor) + HOLD-MSG 해제 후.
>
> 위 스토리 완료 전에는 본 가이드를 **개념 학습 + 단계별 dry-run** 용도로만 사용하고, "10분 내 자치권" 목표 검증은 모든 의존 스토리 완료 후 인수 시점에 수행한다.

> **Story 원문 위치**: 본 문서가 인용하는 "Story X.Y" 파일은 `_bmad-output/implementation-artifacts/` 디렉터리에 있다 (예: `5-1-admin-shell-routing-...md`). 운영 인수 후에는 동일 위치에서 참조 가능.

---

## Step 1 — 관리자 초기 로그인

### 사전 준비

운영 환경의 `.env` 파일에 아래 환경변수가 설정되어 있어야 한다.

```bash
# 위치: 프로젝트 루트의 .env (.env.example 참조)
DENVIA_ADMIN_EMAIL=admin@denvia.local
DENVIA_ADMIN_INITIAL_PASSWORD=change_me_in_production
# ⚠️ DENVIA_ADMIN_PHONE은 현 시점 .env.example·api/src/settings.py 모두 미정의
#    Story 9.2 또는 인수 시점에 다음을 함께 수행:
#    1) .env에 직접 추가: DENVIA_ADMIN_PHONE=01012345678
#    2) api/src/settings.py에 필드 추가: denvia_admin_phone: str | None = None
#    3) Story 5.2/9.2 워커가 이 값을 읽어 80/95/100% 알림톡 수신처로 사용
#    위 절차 완료 전에는 예산 경고 알림톡이 무주소로 발송 실패 → 운영자 인지 불가
DENVIA_ADMIN_PHONE=01012345678
```

### 1.1 관리자 시드 스크립트 실행

```bash
# 1) Docker 환경 기동
docker compose -f infra/docker-compose.yml up -d postgres redis api

# 2-pre) Alembic 현 상태 사전 확인 (롤백 대비)
docker compose -f infra/docker-compose.yml exec api \
  uv --project /workspace/api run alembic current
# 출력 예: 0004_oauth_identity (head) — 이미 head면 다음 명령 skip 가능

docker compose -f infra/docker-compose.yml exec api \
  uv --project /workspace/api run alembic history --verbose | head -20
# 적용 이력 확인 — 부분 적용 의심되면 인수자에게 보고 후 진행

# 2) Alembic 마이그레이션으로 users 테이블 생성 보장
docker compose -f infra/docker-compose.yml exec api \
  uv --project /workspace/api run alembic upgrade head
# 실패 시 롤백: alembic downgrade -1

# 3) seed_admin.py 실행 — 멱등 보장 (이미 존재하면 skip)
docker compose -f infra/docker-compose.yml exec api \
  uv --project /workspace/api run python /workspace/api/scripts/seed_admin.py
# 실행 중 에러 발생 시:
#   (a) DATABASE_URL 미설정 → .env 확인 후 재기동
#   (b) users 테이블 미생성 → 위 단계 2 alembic upgrade head 재실행
#   (c) argon2 해시 실패 → uv 환경 재구성 (uv sync) 후 재실행
#   (d) 부분 INSERT 의심 시: psql로 SELECT * FROM users WHERE role='admin' 확인 후
#       row 있으면 그대로 사용 (멱등), 없으면 재실행
```

기대 출력:

```
[seed_admin] admin 계정 생성 완료: admin@denvia.local
```

또는 이미 존재 시:

```
[seed_admin] admin 계정이 이미 존재합니다 (id=1). skip.
```

### 1.2 첫 로그인

> **(TBD — Story 1.4 완료 / 관리자 셸은 Story 5.1 backlog)**: 현 시점 일반 사용자 로그인은 가능하나 관리자 전용 라우팅(`/admin`)이 미구현이다. 본 단계는 Story 5.1 완료 후 정식 활용된다.

```
브라우저 접속: http://localhost:3000/login (또는 운영 도메인)
이메일: admin@denvia.local
비밀번호: (DENVIA_ADMIN_INITIAL_PASSWORD 값)
```

ASCII 도식:

```
┌──────────────────────────────────┐
│  Denvia 로그인                    │
├──────────────────────────────────┤
│ 이메일: [admin@denvia.local    ] │
│ 비밀번호: [********            ] │
│ [ 로그인 ]                       │
└──────────────────────────────────┘
                ↓
┌──────────────────────────────────┐
│ ⚠️ 비밀번호 변경 필수 안내         │
│  (must_reset_password=true 분기) │
│  ⚠️ 현재 코드는 false로 INSERT —  │
│     §1.3 우회 SQL 먼저 실행 필요 │
│  → 신규 비밀번호 입력 → 저장      │
└──────────────────────────────────┘
                ↓
┌──────────────────────────────────┐
│  /admin/dashboard (Story 5.1)    │
│  ⚠️ Story 5.1 미완료 시 라우트 X │
└──────────────────────────────────┘
```

> ⚠️ **위 도식은 정상 플로우 — 현 시점에는 §1.3 우회 SQL이 사전에 필요하다.**

### 1.3 비밀번호 변경 강제 분기 — 현 구현 상태 안내

> **⚠️ 코드 ↔ 스토리 명세 편차 (AC-10 표기)**:
> - 현 `api/scripts/seed_admin.py:53` 구현은 신규 admin 계정 생성 시 `must_reset_password=false`로 INSERT한다.
> - 본 ONBOARDING 명세는 `must_reset_password=true` 자동 강제 분기를 가정하고 있으나, 해당 분기 미들웨어는 **TBD — Story 5.1(관리자 셸 라우팅)** 또는 별도 후속 스토리에서 구현 예정.
> - **임시 운영 권장 (초기 세팅 전용)**: seed_admin.py 직후 아래 단순 SQL 실행 → 다음 로그인 시 비밀번호 변경 강제됨. 단 `password_hash`는 보존되므로 초기 비밀번호로 1회 로그인 후 변경.
>   ```sql
>   -- 초기 세팅 직후 1회만 실행
>   UPDATE users SET must_reset_password = true WHERE role = 'admin';
>   ```
> - **분실 복구는 다른 절차**: 비밀번호를 분실한 비상 상황은 본 §1.3이 아니라 [`./SECURITY.md`](./SECURITY.md) §3.2.b의 인라인 Python 스크립트(password_hash까지 갱신) 사용. 두 경로의 용도를 혼동하면 초기 비밀번호가 무효화될 수 있음.

`![screenshot](./screenshots/onboarding-step-1-login.png)` *(인수 데모 시 교체)*

---

## Step 2 — 첫 TXT 업로드(RAG 지식베이스)

### 사전 준비 — TXT 파일 포맷

Denvia RAG는 다음 포맷의 TXT만 수용한다.

```
{치주질환 관련}
==초기 잇몸 염증==
잇몸이 붉어지고 양치 시 출혈이 발생하면 초기 치은염을 의심해야 합니다.
정기적인 스케일링과 올바른 칫솔질로 회복 가능합니다.

==진행성 치주염==
치아 주변 골이 흡수되기 시작하는 단계입니다.
치주 치료(SRP)와 정기 검진이 필요합니다.

{보철 관련}
==크라운==
크라운은 손상된 치아 전체를 감싸는 보철입니다.
재료는 PFM, 지르코니아, 골드 등이 있으며 각각의 특징이 다릅니다.
```

규칙:
- 첫 줄: `{대분류}` (중괄호 필수)
- 중분류 시작: `==중분류==` (등호 2개 양쪽)
- 본문: 일반 텍스트 (한 단락은 빈 줄로 구분)
- 인코딩: UTF-8(BOM 없음)
- 한 파일 최대 크기: 10MB

### 2.1 업로드 절차

> **(TBD — Story 8.1 backlog)**: `/admin/rag/data` 라우트 미구현. 본 단계는 Story 8.1 완료 후 활성화.

```
1. /admin/rag/data 접속
2. "TXT 업로드" 버튼 클릭
3. 파일 선택 (예: dental-knowledge-2026-04.txt)
4. 자동 dry-run 검증 → 성공 시 미리보기 화면 표시
   - 추출된 청크 수 (예: 142개)
   - 예상 토큰 수 (예: 38,210 토큰)
5. "지식베이스에 추가" 버튼 클릭
```

ASCII 도식:

```
┌──────────────────────────────────┐
│  /admin/rag/data                 │
│  [ TXT 업로드 ] [ 전체 재빌드 ]  │
├──────────────────────────────────┤
│ 업로드 큐:                       │
│  □ dental-2026-04.txt (대기 중)  │
│  ✓ dental-2026-03.txt (반영 완료)│
└──────────────────────────────────┘
                ↓ 업로드 후
┌──────────────────────────────────┐
│  포맷 검증 결과 (dry-run)         │
│  청크: 142개  예상 토큰: 38,210  │
│  대분류: 치주질환 관련, 보철 관련 │
│  [ 지식베이스에 추가 ]           │
└──────────────────────────────────┘
```

`![screenshot](./screenshots/onboarding-step-2-upload.png)` *(인수 데모 시 교체)*

---

## Step 3 — 첫 재빌드(FAISS 인덱스 갱신)

### 3.1 재빌드 트리거

> **(TBD — Story 8.3 backlog)**: FAISS 스왑 로직 미구현.

업로드 직후 또는 `/admin/rag/data` 메인에서 `[ 전체 재빌드 ]` 버튼 클릭.

확인 모달:
```
전체 재빌드를 시작하시겠습니까?
- 예상 소요 시간: 약 ___분 (청크 수 기준)
- 권장 시간대: 야간 22:00 KST 이후 (FAISS 메모리 피크)
- 진행 중에도 사용자 질의는 정상 응답 (이전 인덱스 유지)
[ 취소 ] [ 시작 ]
```

### 3.2 SSE 진행률 모니터링

`/admin/rag/data` 상단에 진행률 배너가 자동 표시된다.

```
┌──────────────────────────────────────────────┐
│ ▶ 재빌드 진행 중 — 67% (4분 12초 경과)        │
│   [████████████████░░░░░░░░] 67%             │
│   현재 단계: 임베딩 생성 (95/142 청크)        │
└──────────────────────────────────────────────┘
```

내부 동작:
- SSE 채널: `GET /api/v1/admin/events`
- 이벤트: `rag_rebuild_progress`
- 데이터: `{"job_id": ..., "percent": 67, "stage": "embedding", "current": 95, "total": 142}`

### 3.3 완료 확인

1. **진행률 배너**가 100%로 도달 후 사라짐
2. **알림톡 수신**: 관리자 휴대폰으로 `admin.rag_rebuild_completed` 도착 (TBD — Story 8.3 템플릿)
3. **사용자 질의 시험**:
   - 새 탭에서 `/qa` 접속
   - 업로드한 지식 관련 질문(예: "초기 치은염 증상은?") 입력
   - 답변에 새 청크 내용이 반영되었는지 확인

`![screenshot](./screenshots/onboarding-step-3-rebuild.png)` *(인수 데모 시 교체)*

---

## Step 4 — 첫 공지 발송

### 4.1 공지 작성

> **(TBD — Story 7.1 backlog, HOLD-MSG)**: `/admin/content` 라우트 및 RichTextEditor 미구현. 본 단계는 Story 7.1 완료 + HOLD-MSG 해제 후 활성화.

```
1. /admin/content 접속
2. "신규 공지 작성" 버튼 클릭
3. RichTextEditor (Tiptap)에서 본문 작성
   - 제목: 최대 50자
   - 본문: 마크다운 + 이미지 첨부 지원
4. 세그먼트 필터 선택:
   □ 전체 사용자
   □ 치과의사 (doctor)
   □ 치과위생사 (hygienist)
   □ 학생/기타 (student_other)
5. "미리보기" 후 "발송 예약" 또는 "즉시 발송"
```

> ⚠️ **즉시 발송은 회수 불가**: 일단 발송된 공지는 사용자 휴대폰 알림톡으로 즉시 도달하며 철회·정정이 불가능하다. 다음 절차 권장:
> - **반드시 미리보기 단계에서 오타·세그먼트·발송 시점 모두 재확인**
> - **첫 발송은 자기 자신만 포함된 테스트 세그먼트 권장** (관리자 본인 계정만 포함하는 별도 테스트 세그먼트로 사전 검증)
> - **즉시 발송 버튼 클릭 시 2단계 확인 모달 표시**: "본 공지는 회수 불가합니다. {N}명에게 즉시 발송됩니다. 정말 발송하시겠습니까?" — Story 7.1 구현 시 필수 (현 시점 설계 가이드)

ASCII 도식:

```
┌──────────────────────────────────────────────┐
│  /admin/content — 신규 공지 작성              │
├──────────────────────────────────────────────┤
│ 제목: [ 4월 정기 점검 안내                ]  │
│                                              │
│ ┌────────────────────────────────────────┐  │
│ │ [B][I][U]  [H1][H2]  [List]  [Image]   │  │
│ ├────────────────────────────────────────┤  │
│ │ 안녕하세요, Denvia입니다.               │  │
│ │ 다음 주 금요일 22:00~24:00 ...          │  │
│ │                                        │  │
│ └────────────────────────────────────────┘  │
│                                              │
│ 세그먼트:  ☑ doctor  ☑ hygienist  □ s_o   │
│ 발송:     [ 예약 ▼ ] [ 즉시 발송 ]          │
└──────────────────────────────────────────────┘
```

### 4.2 발송 채널 안내

> **⚠️ HOLD-MSG 주의사항 (현 시점)**: 알림톡 발송 경로는 HOLD-MSG 해제 전까지 stub 모드(`MESSAGING_PROVIDER=stub`)이므로 **실제 발송되지 않고 structlog 로그만 기록**된다. 인수자가 알림톡/SMS 공급자 계약 후 실 구현체 확장(§OPERATIONS §6.3)을 완료해야 사용자에게 도달한다.

발송 검증 (stub 모드):

```bash
# API 컨테이너 로그에서 발송 시도 확인
docker compose -f infra/docker-compose.yml logs api | grep "messaging.stub.send_alimtalk"
# 출력 예: phone=****1234 template_code=notice.generic variable_keys=['title','body']
```

`![screenshot](./screenshots/onboarding-step-4-broadcast.png)` *(인수 데모 시 교체)*

---

## 마무리 — 운영 자치권 체크리스트

위 4단계를 모두 완료했다면 다음 운영 작업을 독립 수행할 수 있어야 한다.

- [ ] 관리자 비밀번호 변경 후 정상 로그인 (`/account/password` — **TBD Story 4.3 후 활성화**, 현 시점에는 §1.3 우회 SQL로 `must_reset_password=true` 설정 후 첫 로그인 시 변경 화면)
- [ ] TXT 지식 1건 추가 → 재빌드 → 사용자 질의 반영 확인
- [ ] 공지 1건 작성 → stub 로그에서 발송 시도 확인
- [ ] 일일 KPI 대시보드 항목 위치 식별 (§OPERATIONS §1.1)
- [ ] 알림톡 수신 채널 정상 등록 확인 (§OPERATIONS §1.2 + DENVIA_ADMIN_PHONE 추가 절차)

심화 운영(예산 통제·비상 정지·이상 대응)은 다음 문서를 추가 학습한다:

- 운영 SOP: [`./OPERATIONS.md`](./OPERATIONS.md)
- 이상 대응 플레이북: [`./RUNBOOK_INCIDENT.md`](./RUNBOOK_INCIDENT.md)
- 보안 운영: [`./SECURITY.md`](./SECURITY.md)
- SSOT 편차 결정 기록: [`./adr/0001-ssot-deviations.md`](./adr/0001-ssot-deviations.md)

---

## 검증 이력

| 날짜 | 검증자 | 결과 | 조치 |
|---|---|---|---|
| 2026-04-24 | Hyung woo | 부분 OK — Step 1 시드 스크립트 실재 확인(`api/scripts/seed_admin.py`). `must_reset_password=true` 자동 분기는 코드(`seed_admin.py:53` 기준 false)와 명세 간 편차 발견 → 본 문서에 ⚠️ 경고로 명시. Step 2~4는 해당 라우트(`/admin/rag/data`·`/admin/content`)·UI(Tiptap)·SSE 채널이 모두 미구현이므로 Story 8.1·8.3·7.1 완료 후 실 검증 필요. | 인수 시점에 Story 5.1·8.1·8.3·7.1 완료 후 본 문서 재검증 + 스크린샷 교체 |
| 2026-04-24 | Hyung woo (Story 9.4 AC-7 시나리오 ① Dry-run) | 부분 OK — `seed_admin.py` AST(추상 구문 트리) 정적 파싱 OK. 호스트 Docker daemon 미기동(`Docker Desktop` 실행 필요)으로 실 컨테이너 기동·`alembic upgrade head`·`seed_admin.py` 런타임 실행은 본 검증에서 보류. `must_reset_password=true` 분기 미구현 편차는 본 문서 §1.3에 ⚠️ 경고로 영구 명시. Step 2(TXT 업로드)·Step 3(FAISS 재빌드)는 Story 8.1·8.3 backlog로 Dry-run 불가 → 문서상 절차만 검토 완료. | 인수 시점에 Docker 환경 기동 후 §1.1 명령 3종(`docker compose up` → `alembic upgrade head` → `seed_admin.py`)을 순차 실행하여 실 검증 수행 |
| 2026-04-24 | claude-opus-4-7 (code-review 후속 10건 patch 적용) | OK — 상단 banner(Story 5.1 미완료 시 검증 보류 + Story 원문 위치 안내), §사전준비(DENVIA_ADMIN_PHONE 추가 절차 강화 — settings.py 필드 추가 명시), §1.1(alembic current 사전 확인 + 부분 실패 처리 4종), §1.2 도식(must_reset_password 편차 ⚠️ 도식 내 표기 + Story 5.1 미완료 시 라우트 X), §1.3(우회 SQL 도식화 + 분실 복구는 SECURITY §3.2.b로 분리), §4.1(즉시 발송 회수 불가 경고 + 2단계 확인 모달 명시), 마무리 체크리스트(/account/password Story 4.3 표기), `docs/screenshots/` 디렉터리 신설 + README.md(캡처 가이드) 적용 완료 | — |
