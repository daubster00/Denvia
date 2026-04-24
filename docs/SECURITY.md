# SECURITY — Denvia 보안 운영 SOP

> **최종 수정일:** 2026-04-24
> **작성자:** Hyung woo
> **승인자:** (인수자 검토 시 기입)
> **버전:** v1.0
> **관련 FR/Story:** NFR-S1·S7·C2·C3·C4 / Story 9.4

본 문서는 Denvia 운영 중 보안 관련 표준 작업 절차(SOP)를 정의한다. 환경변수·키 순환·계정 복구·PIPA(개인정보 보호법) 탈퇴 처리·HTTPS·감사 로그·침입 대응의 7개 영역을 다룬다.

> **상위 참조 문서**: 환경변수 전수 목록·배포 절차는 **Story 9.5 — 기술 레퍼런스 문서화** 범위인 `docs/RUNBOOK_DEPLOY.md`에 이관 예정이다. 본 문서는 보안 관점의 핵심 항목만 다룬다.

---

## §1. 환경변수 관리

### 1.1 파일 권한 및 저장 위치

운영 서버에서 `.env` 파일은 다음 권한·위치 규칙을 엄수한다.

```bash
# 권한: owner만 read/write (group/other 차단)
chmod 600 /path/to/denvia/.env
chown denvia:denvia /path/to/denvia/.env

# 위치: 프로젝트 루트(.gitignore에 등재되어 있음)
# Git 추적 금지 — .gitignore 확인 (`.env`, `.env.production`, `.env.staging` 등 모든 변형 점검):
grep -nE "^\.env(\..*)?$" /path/to/denvia/.gitignore
# 기대 출력 예: .env / .env.local / .env.*.local / .env.production
# 만약 .env.staging·.env.development 같은 환경별 파일을 사용하면 .gitignore에 추가 등재 필수
```

### 1.2 현 시점 핵심 환경변수 분류

`.env.example` 파일 기준 분류(인수 시점 전체 목록은 `docs/RUNBOOK_DEPLOY.md` — **TBD Story 9.5**에 이관 예정).

| 분류 | 환경변수 | 민감도 | 비고 |
|---|---|---|---|
| 데이터베이스 | `DATABASE_URL`·`DATABASE_SYNC_URL` | High | DB 접속 자격 증명 |
| Redis | `REDIS_URL` | Medium | 내부망 가정 |
| JWT | `DENVIA_JWT_SECRET` | **Critical** | 최소 32자 무작위 — 노출 시 즉시 §2 키 순환 |
| 관리자 계정 | `DENVIA_ADMIN_EMAIL`·`DENVIA_ADMIN_INITIAL_PASSWORD` | High | 첫 로그인 후 즉시 변경 |
| Sentry | `SENTRY_DSN_API`·`SENTRY_DSN_WEB`·`SENTRY_ENVIRONMENT` | Low | DSN 자체는 PII 미포함. **`SENTRY_DSN_WEB`은 web 빌드 타임 주입(`NEXT_PUBLIC_*` 형식 환경변수) — 백엔드 컨테이너 재시작 무영향, web 이미지 재빌드 필요.** `SENTRY_DSN_API`만 `api/src/settings.py`가 로드 |
| OpenAI | `OPENAI_API_KEY` | **Critical** | 노출 시 비용 폭증·즉시 폐기·재발급 |
| OAuth | `KAKAO_*`·`GOOGLE_*`·`NAVER_*` (CLIENT_ID·SECRET·REDIRECT_URI) | High | 인수 시점에 클라이언트 키로 교체 |
| 메시징 | `MESSAGING_PROVIDER`·`ALIMTALK_TEMPLATE_MAP_JSON` | Medium | 공급자 키는 HOLD-MSG 해제 후 추가 |

### 1.3 Oracle Vault 전환 — Post-MVP 로드맵

> **본 개발 범위 외**: 현 MVP는 평문 `.env` 파일 + `chmod 600` 권한 모델로 운영한다. 운영 규모 확대 시(예: 멀티 인스턴스, 키 순환 자동화, 감사 추적 강화) Oracle Cloud Vault 또는 동급 Secret Manager로 이전 권장.

이전 시점 결정 기준:
- 운영 인스턴스 수 ≥ 3
- 키 순환 주기 ≤ 분기 1회
- 외부 보안 감사 요구사항 발생

---

## §2. 비밀번호·빌링키 키 순환 절차

### 2.1 argon2id 파라미터 변경

비밀번호 해시는 `argon2-cffi`의 argon2id 알고리즘을 사용한다(`api/src/utils/argon2.py` 또는 `seed_admin.py:8`의 `PasswordHasher` 활용).

파라미터 변경 시 절차:
1. **변경 검토**: 메모리·시간 비용 상향 시 인증 응답 시간(p95) 영향 측정
2. **점진적 재해시**: 사용자 로그인 성공 시 백그라운드에서 신규 파라미터로 재해시 후 DB 갱신(seamless rotation)
3. **재로그인 강제(필요 시)**: 보안 인시던트로 즉시 재해시가 필요하면 `users.must_reset_password = true` 일괄 UPDATE → 다음 로그인 시 비밀번호 변경 강제

```sql
-- 전체 사용자 비밀번호 재설정 강제 (보안 인시던트 시)
-- ⚠️ 반드시 단일 트랜잭션으로 묶어서 실행 (UPDATE 적용 후 INSERT 실패 시 감사 공백 방지)
-- ⚠️ audit_logs 테이블이 미생성(Story 5.1 backlog) 상태에서는 두 번째 INSERT가 실패하므로
--    Story 5.1 완료 전에는 UPDATE만 별도 실행 + 감사는 외부 노트(인시던트 티켓)에 수기 기록
BEGIN;

UPDATE users
SET must_reset_password = true, updated_at = NOW()
WHERE role IN ('user', 'admin');

-- 감사 로그 기록 (NFR-S7) — Story 5.1 완료 후에만 실행 가능
INSERT INTO audit_logs (action, actor_id, target_type, target_id, payload, created_at)
SELECT 'security.bulk_password_reset', NULL, 'system', NULL,
       jsonb_build_object('reason', '인시던트 ID', 'count', COUNT(*)), NOW()
FROM users WHERE role IN ('user', 'admin');

COMMIT;
-- (TBD: audit_logs 테이블은 Story 5.1에서 생성 — 미생성 상태에서는 INSERT 라인을 주석 처리하고
--       UPDATE만 BEGIN/COMMIT으로 묶어 실행할 것)
```

### 2.2 빌링키 암호화 키(`BILLING_KEY_ENCRYPTION_KEY`) 순환

> **(TBD — Epic 3 HOLD-PG)**: 빌링키 저장 로직 미구현. 본 절차는 Story 3.2(빌링키 발급) 완료 후 활성화.

순환 스케줄: **연 1회 권장** (또는 보안 인시던트 발생 즉시).

절차:
1. 신규 키 생성: `openssl rand -base64 32`
2. **이중 키 운영 기간 1주**: 신규 키로 신규 빌링키 암호화, 기존 키로 기존 빌링키 복호화 (점진 마이그레이션)
3. 1주 경과 후 모든 빌링키를 신규 키로 재암호화
4. 기존 키 폐기 + `audit_logs`에 액션 코드 `security.billing_key_rotated` 기록

### 2.3 JWT 시크릿 순환

`DENVIA_JWT_SECRET` 순환 시 모든 사용자 세션이 무효화된다(전체 강제 로그아웃).

절차:
1. 신규 시크릿 생성: `openssl rand -base64 64`
2. `.env` 갱신 + 컨테이너 재시작
3. **사용자 영향**: 모든 기존 JWT 토큰이 401 응답 → 클라이언트 자동 로그아웃 후 재로그인 화면으로 전환
4. 사전 공지 권장(점검 안내) — 비상시(키 노출)에는 즉시 순환

#### 2.3.1 사전 공지 채널 — HOLD-MSG 미해제 시 대체 경로

알림톡 브로드캐스트(Story 7.1) 미구현 + HOLD-MSG 미해제 상태에서는 사용자 알림 경로가 제한적이다. 다음 대체 채널 활용:

| 우선순위 | 채널 | 적용 |
|---|---|---|
| 1 | **메인터넌스 페이지 임시 노출** | Nginx에서 503 응답 + 안내 HTML로 1~2분 차단. 사용자가 즉시 인지 |
| 2 | **로그인 화면 상단 배너** (Story 7.2 popup 활성화) | "{날짜 시간} 보안 점검으로 재로그인 필요" 공지 |
| 3 | **API 응답 헤더 `X-Maintenance-Notice`** | 클라이언트가 다음 요청 시 안내 모달 노출 (web 클라이언트 패치 필요) |
| 4 | **클라이언트(인수자) 직접 통보** | 위 채널 모두 실효성 없으면 클라이언트가 알고 있는 사용자 채널(이메일·SMS — 단 본 서비스 외부 채널)로 안내 |

**비상 순환 (키 노출 등)** — 사전 공지 생략하고 즉시 순환 후 사후 공지로 대체.

---

## §3. 관리자 계정 분실 복구

### 3.1 시나리오: 단일 관리자가 비밀번호 분실 + 비밀번호 재설정 SMS도 수신 불가

서비스에는 **단일 관리자 모델**이 적용되어 있으므로 관리자 계정 분실은 운영 차단 상태로 직결된다. 본 절차는 비상시 직접 DB 접근으로 복구하는 표준 방법이다.

> **본 §3 절차는 "비밀번호 분실 비상 복구" 전용**이다. 인수 직후 초기 세팅 시 `must_reset_password=true`만 강제하려면 ONBOARDING §1.3의 단순 SQL(`UPDATE users SET must_reset_password=true WHERE role='admin'`)을 사용한다. 두 경로의 차이:
> - **ONBOARDING §1.3** — `password_hash` 보존, 다음 로그인 시 변경 강제 (초기 세팅용)
> - **본 SECURITY §3** — `password_hash` 자체를 신규 비밀번호로 덮어쓰기 (분실 복구용)

### 3.2 복구 명령

> ⚠️ **순서 안내**: 아래 절차는 `seed_admin.py` 재실행이 도움이 되지 **않는다**(멱등 가드로 skip). 곧바로 §3.2.b 인라인 스크립트로 비밀번호를 재설정하라.

```bash
# 1) Docker 컨테이너 진입 (DB 직접 접근 가능한 운영자 계정 사용)
docker compose -f infra/docker-compose.yml exec api bash

# 2) (참고) seed_admin.py는 멱등 가드(SELECT ... WHERE role='admin')로
#    기존 admin이 존재하면 무조건 skip — 비밀번호 재설정에는 사용 불가.
#    바로 아래 §3.2.b 인라인 스크립트를 사용한다.
```

#### §3.2.b 비밀번호 재설정 인라인 스크립트

```bash
# 3-a) 임시 비밀번호 입력 — bash history·ps에 노출되지 않도록 read -rs 사용
read -rs -p "신규 임시 비밀번호 입력 (입력 내용 숨김): " NEW_PWD
echo
export NEW_PWD

# 3-b) 인라인 Python — sys.path 조작으로 api.src 모듈 import 보장
#      (seed_admin.py:15 패턴과 동일)
uv --project /workspace/api run python -c "
import asyncio, os, sys
sys.path.insert(0, '/workspace')  # 'api.src.*' import 경로 보장
from argon2 import PasswordHasher
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from api.src.settings import settings

async def reset():
    new_pwd = os.environ['NEW_PWD']
    ph = PasswordHasher()
    h = ph.hash(new_pwd)
    eng = create_async_engine(settings.database_url)
    sf = async_sessionmaker(eng, expire_on_commit=False)
    async with sf() as s:
        result = await s.execute(text(\"\"\"
            UPDATE users
            SET password_hash = :h, must_reset_password = true, updated_at = NOW()
            WHERE role = 'admin'
        \"\"\"), {'h': h})
        await s.commit()
        if result.rowcount == 0:
            raise SystemExit('ERROR: admin row not found — seed_admin.py 먼저 실행 필요')
        print(f'admin password reset OK (rowcount={result.rowcount}); must_reset_password=true on next login')
    await eng.dispose()

asyncio.run(reset())
"

# 4) 환경변수 즉시 제거 (다음 명령에서 노출 방지)
unset NEW_PWD
```

> **추후 정식화**: 위 임시 절차는 인수 시점에 `api/scripts/seed_admin.py --reset-password` CLI 옵션으로 정식화될 예정이나 현 시점 미구현. **TBD — 별도 인프라 개선 스토리 또는 인수자 요청 시 작성**.

### 3.3 감사 로그 기록 의무

비상 복구 작업은 반드시 별도 감사 로그를 남긴다.

```sql
INSERT INTO audit_logs (action, actor_id, target_type, target_id, payload, created_at)
VALUES (
  'admin.password.manual_reset',
  NULL,                          -- 시스템 작업 (수행자는 payload에 기록)
  'user',
  (SELECT id FROM users WHERE role = 'admin' LIMIT 1),
  jsonb_build_object(
    'reason', '관리자 비밀번호 분실로 인한 직접 복구',
    'performed_by', '운영자 식별 정보',  -- 인수자 기입
    'incident_ticket', 'TICKET-XXX'      -- 있으면 기재
  ),
  NOW()
);
-- (TBD: audit_logs 테이블은 Story 5.1에서 생성)
```

---

## §4. PIPA(개인정보 보호법) 탈퇴 처리 감사

### 4.1 30일 내 PII 파기 정책(NFR-C2·C3·C4)

> **(TBD — Story 1.7 backlog)**: 탈퇴 플로우 미구현. 본 절차는 Story 1.7 완료 후 활성화.

사용자 탈퇴 요청 시 30일 내 파기 대상:

| 데이터 | 파기 방식 | 보존 사유 |
|---|---|---|
| `users.email` | NULL 처리(또는 임의 해시 대체) | 재가입 방지 (선택) |
| `users.phone` | NULL 처리 | — |
| `users.password_hash` | NULL 처리 | — |
| `qa_logs.user_id` | NULL 처리 (익명화) | 통계 목적 본문은 보존 |
| `qa_logs.question_text` | 그대로 보존 | 본문은 PII 미포함 가정(NFR-C3) |
| `audit_logs` (탈퇴 액션) | 1년 보존 후 영구 삭제 | NFR-S7 |

### 4.2 탈퇴 처리 검증 체크리스트

탈퇴 요청 후 30일 경과 시점에 다음 SQL로 검증한다.

```sql
-- 1. 탈퇴 요청 후 30일 경과 사용자 식별
SELECT id, withdrawn_at
FROM users
WHERE withdrawn_at IS NOT NULL
  AND withdrawn_at <= NOW() - INTERVAL '30 days'
  AND email IS NOT NULL;  -- 파기 누락 사용자 (있으면 안 됨)

-- 2. 본 사용자들의 PII 파기 확인 (위 쿼리가 0건이어야 정상)

-- 3. qa_logs 익명화 확인
SELECT COUNT(*)
FROM qa_logs
WHERE user_id IN (SELECT id FROM users WHERE withdrawn_at <= NOW() - INTERVAL '30 days');
-- 기대: 0 (모두 user_id=NULL로 익명화)
-- (TBD: qa_logs 테이블은 Story 2.1에서 생성)

-- 4. 감사 로그 누락 확인
SELECT action, COUNT(*)
FROM audit_logs
WHERE action IN ('user.withdrawal.requested', 'user.pii.purged')
  AND created_at >= NOW() - INTERVAL '60 days'
GROUP BY action;
-- 기대: 두 액션 카운트가 동일 (요청 = 파기)
-- (TBD: audit_logs 테이블은 Story 5.1에서 생성)
```

### 4.3 retention worker

> **(TBD — `api/src/workers/retention_tasks.py` 미존재)**: 현 시점 `api/src/workers/`에는 `celery_app.py`·`notification_tasks.py`만 존재. retention 워커는 Story 1.7 또는 별도 후속 스토리에서 생성 예정.

기대 동작:
- Celery beat 일일 1회 스케줄 실행
- 30일 경과 탈퇴자 PII 자동 파기 + `qa_logs.user_id=NULL` 익명화
- 1년 경과 `audit_logs` 행 영구 삭제
- 처리 결과 structlog `retention.purge.summary` 키로 기록

#### 4.3.1 worker 미구현 기간 — 임시 수동 purge SQL (PIPA 위반 방지)

Story 1.7·retention worker 완료 전에 탈퇴 사용자가 발생할 수 있다. 30일 파기 자동화가 없는 상태이므로 운영자가 **주 1회 수동 실행** 필요.

```sql
-- ⚠️ 단일 트랜잭션 + 사전 카운트 확인 + 백업 권장
BEGIN;

-- (a) 30일 경과 탈퇴자 카운트 확인 (실행 전 백업 대상 파악)
SELECT COUNT(*) AS to_purge
FROM users
WHERE withdrawn_at IS NOT NULL
  AND withdrawn_at <= NOW() - INTERVAL '30 days'
  AND email IS NOT NULL;

-- (b) PII 파기 — users 테이블
UPDATE users
SET email = NULL,
    phone = NULL,
    password_hash = NULL,
    updated_at = NOW()
WHERE withdrawn_at IS NOT NULL
  AND withdrawn_at <= NOW() - INTERVAL '30 days'
  AND email IS NOT NULL;

-- (c) qa_logs 익명화 — Story 2.1 완료 후에만 적용
-- UPDATE qa_logs SET user_id = NULL
-- WHERE user_id IN (SELECT id FROM users WHERE withdrawn_at <= NOW() - INTERVAL '30 days');

-- (d) audit_logs 1년 경과 행 영구 삭제 — Story 5.1 완료 후에만 적용
-- DELETE FROM audit_logs WHERE created_at <= NOW() - INTERVAL '1 year';

COMMIT;
```

운영자 체크리스트:
- [ ] 매주 월요일 §4.3.1 카운트 확인 → 0건 아니면 (b) 실행
- [ ] 실행 결과 운영 노트(외부 도구·스프레드시트)에 `날짜 · 처리 건수` 기록 (audit_logs 미생성 기간의 감사 보완)
- [ ] retention worker 정식 가동(Story 1.7 완료) 후 본 수동 절차 폐기

---

## §5. HTTPS 인증서 자동 갱신 모니터링(NFR-S1)

### 5.1 Let's Encrypt certbot 자동 갱신

> **(TBD — Story 1.1 운영 환경 정비 시 cron 설정)**: 현 시점 `infra/nginx/` 구성은 존재하나 certbot 자동 갱신 cron 설정은 인수 시 운영 환경에서 추가 필요.

표준 자동 갱신 메커니즘:

```bash
# crontab -l (운영 서버)
0 3 * * * certbot renew --quiet --post-hook "systemctl reload nginx"

# 또는 systemd timer (현대 배포 권장):
systemctl status certbot.timer
systemctl list-timers | grep certbot
```

### 5.2 갱신 상태 확인

```bash
# 마지막 갱신 결과 확인
sudo certbot certificates

# 출력 예시:
# Certificate Name: denvia.example.com
#   Domains: denvia.example.com
#   Expiry Date: 2026-07-22 09:13:42+00:00 (VALID: 89 days)
#   Certificate Path: /etc/letsencrypt/live/denvia.example.com/fullchain.pem
```

만료 30일 이내 + 자동 갱신 실패 시 즉시 §5.3 수동 갱신.

### 5.3 수동 갱신 절차

> **사전 결정**: certbot 갱신 모드를 먼저 확인하라. **webroot/HTTP-01 모드면 Nginx 정지 불필요**(다운타임 0). **standalone 모드면 80포트 점유 충돌로 정지 필요**.
>
> 확인 명령:
> ```bash
> sudo certbot certificates  # 출력의 "Authenticator" 또는 cert 발급 시 사용 plugin 확인
> # 또는
> ls /etc/letsencrypt/renewal/*.conf  # [renewalparams] authenticator = webroot|standalone
> ```

#### (a) webroot 모드 (권장 — Nginx 정지 불필요)

```bash
# Nginx 가동 상태 그대로 갱신 시도
sudo certbot renew --force-renewal

# Nginx에 신규 인증서 적용
docker compose -f infra/docker-compose.yml exec nginx nginx -s reload

# HTTPS 동작 확인
curl -I https://denvia.example.com/
```

#### (b) standalone 모드 (Nginx 정지 필요 — 다운타임 발생)

```bash
# 1) Nginx 일시 정지
docker compose -f infra/docker-compose.yml stop nginx

# 2) 갱신 강제 시도
sudo certbot renew --force-renewal

# 3) Nginx 재시작
docker compose -f infra/docker-compose.yml start nginx

# 4) HTTPS 동작 확인
curl -I https://denvia.example.com/
```

#### (c) 갱신마저 실패한 경우 — 골든 윈도우 결정 트리

| 상황 | 조치 |
|---|---|
| 만료 7일 이상 + 갱신 실패 | DNS 설정·디스크 용량·certbot 로그(`/var/log/letsencrypt/letsencrypt.log`) 확인 후 (a) 재시도 |
| 만료 24시간 이내 + 갱신 실패 | 임시 메인터넌스 페이지(HTTP 503 + 안내 HTML)로 전환, 사용자에게 "보안 인증서 갱신 중" 공지. HTTP 평문 서빙은 **금지**(쿠키 `secure` 플래그로 세션 전송 실패 + 보안 위험) |
| 만료 후 + 갱신 실패 | 사용자가 브라우저 경고 마주침 → 즉각 메인터넌스 페이지 전환 + 클라이언트(인수자) 보고 |

### 5.4 모니터링 알림

**만료 14일 전 알림 표준 구성** (인수 직후 구축 권장):

(a) **certbot deploy-hook + 알림톡 발송** (자체 시스템 활용):
```bash
# /etc/letsencrypt/renewal-hooks/deploy/notify.sh
#!/usr/bin/env bash
# 갱신 성공 시 알림톡 발송 (Story 4.1 stub 또는 실 어댑터)
docker compose -f infra/docker-compose.yml exec api \
  python -m api.scripts.notify_admin "HTTPS 인증서 갱신 완료: $(date +%Y-%m-%d)"
```

(b) **외부 모니터링 서비스** (운영 단순):
- UptimeRobot SSL 만료 알림 (무료 50개 모니터)
- 또는 Sentry 자체 cron monitor + 만료 D-14 webhook

**만료 임박(D-3) 자동 차단 권장 — 자동 갱신이 3회 이상 실패하면 운영자에게 즉시 알림톡 + 수동 갱신 SOP(§5.3) 트리거.**

---

## §6. 감사 로그 1년 보관 규정(NFR-S7)

### 6.1 보관 정책

`audit_logs` 테이블에 기록되는 모든 행은 **created_at 기준 1년 보관 후 영구 삭제**한다. 본 정책은 PIPA 최소 보유 원칙과 운영 추적성 사이의 균형으로 설정되었다.

> **(TBD — `audit_logs` 테이블은 Story 5.1에서 생성)**: 본 시점 미존재. retention worker도 §4.3과 동일하게 미구현.

### 6.2 보존 대상 액션 — 아키텍처 Patch 4 최종 목록

다음 8종 기능명세서 액션은 반드시 `audit_logs`에 기록된다.

| 액션 코드 | 출처 | 설명 |
|---|---|---|
| `A-202` | 기능명세서 | 사용자 권한 변경(차단·해제·세그먼트 변경) |
| `A-301` | 기능명세서 | 결제 기록(승인·취소) |
| `A-302` | 기능명세서 | 환불 기록(자동·수동) |
| `A-401` | 기능명세서 | 공지 발송(관리자 push) |
| `A-402` | 기능명세서 | 팝업 활성/비활성 |
| `A-403` | 기능명세서 | 글로벌 토글 변경(쿼터·지연) |
| `A-404` | 기능명세서 | 운영 정책 변경(일일 쿼터·월 예산) |
| `A-502` | 기능명세서 | 예산 경고 + kill-switch 발동/해제 |

### 6.3 retention worker 일일 실행 확인

> **(TBD — `api/src/workers/retention_tasks.py` 미존재)**

기대 동작 검증:
```bash
# Celery beat 스케줄 확인 (정상 운영 시)
docker compose -f infra/docker-compose.yml exec beat \
  celery -A api.src.workers.celery_app inspect scheduled | grep retention

# 일일 실행 결과 로그
docker compose -f infra/docker-compose.yml logs worker | grep "retention.purge.summary"
# 출력 예: deleted=12 retained=345 elapsed_ms=82
```

### 6.4 감사 로그 무결성 검증(주기 점검)

```sql
-- 최근 7일간 액션 카테고리별 카운트
SELECT action, COUNT(*) AS cnt
FROM audit_logs
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY action
ORDER BY cnt DESC;

-- 누락 의심 액션 확인 — 결제 발생 vs A-301 감사 기록 카운트 비교 (일별)
-- (TBD: payments 테이블은 Story 3.x에서 생성)
WITH pay_daily AS (
  SELECT DATE(created_at) AS d, COUNT(*) AS pay_cnt
  FROM payments
  WHERE status = 'success' AND created_at >= NOW() - INTERVAL '30 days'
  GROUP BY DATE(created_at)
),
audit_daily AS (
  SELECT DATE(created_at) AS d, COUNT(*) AS audit_cnt
  FROM audit_logs
  WHERE action = 'A-301' AND created_at >= NOW() - INTERVAL '30 days'
  GROUP BY DATE(created_at)
)
SELECT
  COALESCE(p.d, a.d) AS day,
  COALESCE(p.pay_cnt, 0) AS payments,
  COALESCE(a.audit_cnt, 0) AS audits,
  COALESCE(p.pay_cnt, 0) - COALESCE(a.audit_cnt, 0) AS gap
FROM pay_daily p FULL OUTER JOIN audit_daily a ON p.d = a.d
WHERE COALESCE(p.pay_cnt, 0) <> COALESCE(a.audit_cnt, 0)
ORDER BY day DESC;
-- 기대: 결과 0건 (모든 일자에서 결제 = 감사 카운트 일치)
-- 결과가 나오면: 해당 일자 application 로그 분석 필요 (auditor 미들웨어 누락 또는 트랜잭션 롤백 가능성)
```

동일 패턴을 다른 액션 코드에도 적용 가능:
- `A-302`(환불) vs `payments WHERE status='refunded'`
- `A-401`(공지 발송) vs `notification_queue WHERE channel='alimtalk' AND template LIKE 'notice.%'`
- `A-502`(kill-switch 발동/해제) vs `killswitch_states` INSERT/UPDATE 카운트

---

## §7. 침입 대응 초동 조치 SOP

### 7.1 의심 로그인 시도 감지

기준: **동일 IP에서 5분 이내 로그인 실패 5회 이상**.

> **(부분 TBD)**: Story 1.4(이메일 로그인) AC에 brute-force 로그 기록이 포함되어 있어 `auth.login.failed` 액션은 기록 가능. 단, 자동 IP 차단 로직은 별도 후속 스토리(인수자 요청 시) 예정.

탐지 쿼리:
```sql
-- 최근 1시간 의심 IP 식별
SELECT
  payload->>'ip' AS suspect_ip,
  COUNT(*) AS fail_count
FROM audit_logs
WHERE action = 'auth.login.failed'
  AND created_at >= NOW() - INTERVAL '1 hour'
GROUP BY payload->>'ip'
HAVING COUNT(*) >= 5
ORDER BY fail_count DESC;
-- (TBD: audit_logs 테이블은 Story 5.1에서 생성)
```

### 7.2 수동 IP 차단

Nginx 레이트 리밋 설정 임시 강화:
```nginx
# infra/nginx/snippets/blocked-ips.conf (신설 — RUNBOOK §⑥와 동일 경로 사용)
deny 1.2.3.4;          # 차단 대상 IP
deny 5.6.7.0/24;       # 대역 차단

# infra/nginx/denvia.conf 상단에 include 추가:
# include /etc/nginx/snippets/blocked-ips.conf;
```

적용:
```bash
docker compose -f infra/docker-compose.yml exec nginx nginx -t       # 문법 검증
docker compose -f infra/docker-compose.yml exec nginx nginx -s reload # 무중단 적용 (restart 금지)
```

차단 시 즉시 audit_logs 기록(트랜잭션 외 이슈 추적용):
```sql
INSERT INTO audit_logs (action, actor_id, target_type, target_id, payload, created_at)
VALUES ('security.ip_blocked', NULL, 'ip', NULL,
        jsonb_build_object('ip', '1.2.3.4', 'reason', '브루트포스 의심', 'incident_ticket', 'TICKET-XXX'),
        NOW());
-- (TBD: audit_logs 테이블은 Story 5.1에서 생성)
```

### 7.2.1 IP 차단 해제 절차 (오탐 대응)

차단된 IP가 정상 사용자(예: 기업 공용 NAT)로 판명될 수 있으므로 **주 1회 차단 목록 리뷰** 권장.

```bash
# 1) 현재 차단 목록 확인
cat infra/nginx/snippets/blocked-ips.conf

# 2) 해제 대상 라인 삭제 (편집기 또는 sed)
sed -i '/^deny 1\.2\.3\.4;/d' infra/nginx/snippets/blocked-ips.conf

# 3) 무중단 적용
docker compose -f infra/docker-compose.yml exec nginx nginx -t
docker compose -f infra/docker-compose.yml exec nginx nginx -s reload
```

해제 시 감사 로그:
```sql
INSERT INTO audit_logs (action, actor_id, target_type, target_id, payload, created_at)
VALUES ('security.ip_unblocked', NULL, 'ip', NULL,
        jsonb_build_object('ip', '1.2.3.4', 'reason', '오탐 확인 — 정상 사용자',
                           'reviewed_by', '운영자 식별'),
        NOW());
```

차단 목록 정기 리뷰 SOP:
- [ ] 매주 월요일 `blocked-ips.conf` 라인 수 확인
- [ ] 30일 이상 된 단일 IP 차단(대역 차단 제외)은 자동 해제 후보로 검토
- [ ] 영향받는 사용자 문의가 들어오면 즉시 해제 + 사유 audit 기록

### 7.3 Sentry 에스컬레이션

1. Sentry에 이슈 수동 생성: 제목 "[Security] Suspect brute-force from {IP}"
2. 태그: `security`, `auth`, `incident`
3. 첨부:
   - 차단 IP 목록
   - 시간대별 실패 분포 그래프
   - 영향받은 사용자 계정(있는 경우)

### 7.4 클라이언트 보고

다음 경우 즉시 클라이언트(인수자) 보고:
- 의심 IP가 단순 봇이 아닌 표적 공격으로 판단되는 경우
- 실제 계정 탈취 의심 사례 발견(성공 로그인 패턴 이상)
- 데이터 유출 우려가 있는 경우(예: PII 조회 API 비정상 호출 분포)

보고 채널: 인수자 휴대폰 번호 — **(인수자 기입)**

---

## 검증 이력

| 날짜 | 검증자 | 결과 | 조치 |
|---|---|---|---|
| 2026-04-24 | Hyung woo | OK — 7개 섹션 모두 게재. 인용 파일 경로(`api/scripts/seed_admin.py`·`api/src/settings.py`·`api/src/utils/argon2.py`·`infra/docker-compose.yml`·`infra/nginx/`·`.env.example`·`.gitignore`) 모두 실재 검증. 미존재 항목(`api/src/workers/retention_tasks.py`·`audit_logs`·`payments`·`qa_logs` 테이블·`/admin/*` 관리자 라우트·`seed_admin.py --reset-password` CLI 옵션) 모두 `(TBD — Story X.Y)` 표기로 명시. | — |
| 2026-04-24 | claude-opus-4-7 (code-review 후속 12건 patch 적용) | OK — §1.1(.gitignore grep 정규식 보강), §1.2(SENTRY_DSN_WEB 빌드 타임 주입 안내), §2.1(트랜잭션 + audit_logs 미존재 분기), §2.3.1(JWT 순환 HOLD-MSG 대체 채널 4종), §3.2.b(read -rs + sys.path + rowcount 검증 + unset NEW_PWD), §4.3.1(retention worker 미구현 기간 수동 purge SQL), §5.3(webroot/standalone 결정 트리 + 갱신 실패 골든 윈도우), §5.4(certbot deploy-hook + UptimeRobot 권장), §6.4(payments vs A-301 카운트 비교 SQL), §7.2(nginx -s reload + 차단 audit log), §7.2.1(IP 해제 절차 + 정기 리뷰 SOP) 적용 완료 | — |
