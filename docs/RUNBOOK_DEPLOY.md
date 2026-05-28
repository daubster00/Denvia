# 배포·CI/CD 런북

> **최종 수정일:** 2026-04-24
> **작성자:** Hyung woo
> **승인자:** (인수자 검토 시 기입)
> **버전:** v1.0
> **관련 FR/Story:** NFR-SC3 / Story 9.5a

---

## §1. Oracle VM 초기 프로비저닝

Oracle Always Free VM(Oracle Linux 9 가정) 최초 설정 절차.

> VM 사양(인수자 기입): CPU _____ / RAM _____ GB / 스토리지 _____ GB

```bash
# 1. SSH 키 등록 — Oracle Cloud Console에서 공개 키 등록 후 접속
ssh -i ~/.ssh/your_private_key opc@<VM_PUBLIC_IP>

# 2. Docker 및 Compose Plugin 설치 (Oracle Linux 9)
sudo dnf install -y docker docker-compose-plugin git

# 3. Docker 서비스 시작 및 자동 시작 등록
sudo systemctl enable --now docker
sudo usermod -aG docker $USER

# 4. 저장소 클론
git clone https://github.com/<your-org>/dental-chatbot.git /opt/denvia
cd /opt/denvia

# 5. 환경변수 파일 생성 (.env.example 복사 후 실값 주입)
cp .env.example .env
nano .env   # 아래 §7 환경변수 목록 참조

# 6. 방화벽 포트 개방 (Oracle Linux 기본 방화벽 + OCI Security List 양쪽 모두)
sudo firewall-cmd --permanent --add-port=22/tcp
sudo firewall-cmd --permanent --add-port=80/tcp
sudo firewall-cmd --permanent --add-port=443/tcp
sudo firewall-cmd --reload
```

> **NFR-SC3 재인용**: 청크 ≥ 10만·OOM·p95 초과 트리거 발생 시 VM 스케일업 또는 FAISS 파티셔닝을 검토한다.
> **WDS 로컬 벤더 주의**: `pnpm add @wanteddev/...` 금지. `vendor/montage-web/` 로컬 패키지를 사용한다.

---

## §2. `infra/docker-compose.prod.yml` 구동

실재 파일(`infra/docker-compose.prod.yml`)의 서비스 목록: `web`, `api`, `worker`, `beat`, `postgres`, `redis`, `nginx`.

```bash
# 프로젝트 루트에서 실행
cd /opt/denvia

# 이미지 빌드 및 컨테이너 시작
docker compose -f infra/docker-compose.prod.yml up -d --build

# 헬스체크 대기 (postgres·redis healthcheck 통과까지)
docker compose -f infra/docker-compose.prod.yml ps

# 로그 실시간 확인
docker compose -f infra/docker-compose.prod.yml logs -f

# 개별 서비스 로그 확인
docker compose -f infra/docker-compose.prod.yml logs -f api
```

**서비스별 역할**:

| 서비스 | 역할 | 구현 상태 |
|---|---|---|
| `web` | Next.js SSR 서버 | ✅ |
| `api` | FastAPI 앱 서버 | ✅ (auth·me·health 라우터) |
| `worker` | Celery 비동기 워커 | 🟡 알림 태스크 2건 실재, 결제 재시도 ⏳ Story 3.4 |
| `beat` | Celery 스케줄러 | 🟡 구조만, 실 태스크 Story 4.1 |
| `postgres` | PostgreSQL 16 | ✅ |
| `redis` | Redis 7 (DB 0~4 고정 용도) | ✅ |
| `nginx` | 리버스 프록시 + TLS 종단 | ✅ (prod 설정) |

---

## §3. Nginx·certbot 설정

### 실재 파일

- `infra/nginx/nginx.conf` ✅
- `infra/nginx/denvia.conf` ✅
- `infra/nginx/snippets/security-headers.conf` ✅
- `infra/nginx/snippets/sse-proxy.conf` ✅

### Let's Encrypt 인증서 최초 발급 (1회)

```bash
# certbot 설치 (Oracle Linux)
sudo dnf install -y certbot python3-certbot-nginx

# 인증서 발급 (Nginx 플러그인 사용)
sudo certbot --nginx -d <your-domain.com>

# 자동 갱신 확인
sudo certbot renew --dry-run
```

> 자동 갱신 cron 설정은 `docs/SECURITY.md` §5(Story 9.4)에서 관리한다.

---

## §4. CI 파이프라인

### 실재 워크플로우 파일

- `.github/workflows/ci.yml` ✅ — ESLint·TypeScript·Vitest + Ruff·Mypy·Pytest
- `.github/workflows/codeql.yml` ✅ — 코드 보안 스캔
- `.github/workflows/release.yml` ✅ — 릴리즈 자동화

### `ci.yml` 잡 구성

| 잡 | 성공 조건 |
|---|---|
| `pathspec-check` | RAG 경로 변경 감지 (아래 참조) |
| `web` | ESLint + TypeScript `--noEmit` + Vitest 단위 테스트 |
| `api` | Ruff lint + Mypy + Pytest (postgres·redis 서비스 포함) |

### `pathspec-check` 재설정 예정

**현 2026-04-24 상태**: `.github/workflows/ci.yml:11-26` 잡의 패턴 `^RAG 코드/`가 실제 디렉터리 경로 `자료/RAG 코드/`와 불일치하여 **사실상 no-op — 어떤 PR도 차단하지 않는다.**

```yaml
# 현재 ci.yml:22 (no-op)
if echo "$CHANGED" | grep -q "^RAG 코드/"; then
```

**Story 2.1 착수 PR에서 동시 수행**:
- (a) 경로 이전: `자료/RAG 코드/` → `vendor/rag/`
- (b) `pathspec-check` 재설정: 자동 차단(exit 1) → 라벨 `rag-modified` + CODEOWNERS 수동 승인 방식으로 전환

---

## §5. 배포 롤백

```bash
# 이전 이미지 태그로 특정 서비스 교체
docker compose -f infra/docker-compose.prod.yml stop api
docker tag <previous-image>:<tag> denvia-api:latest
docker compose -f infra/docker-compose.prod.yml up -d api
```

**Alembic downgrade 주의사항**:
- `downgrade`는 데이터 손실을 유발할 수 있다.
- downgrade 전 반드시 `pg_dump`로 백업을 수행한다 (§8 참조).

```bash
# 1. 백업 먼저
pg_dump -U denvia -F c denvia > backup_before_rollback_$(date +%Y%m%d).dump

# 2. 특정 revision으로 downgrade
cd api && uv run alembic downgrade <revision>
```

---

## §6. DB 마이그레이션 실행·롤백

### 현재 revision 목록 (`api/alembic/versions/`)

| revision 파일 | 설명 |
|---|---|
| `0001_initial_users.py` | 초기 users 테이블 |
| `0002_notification_queue.py` | 알림 대기열 테이블 |
| `0003_anomaly_events.py` | 이상 이벤트 테이블 |
| `0004_oauth_identity.py` | OAuth 아이덴티티 테이블 |

### 실행 명령

```bash
# 최신 상태로 업그레이드
cd api && uv run alembic upgrade head

# 특정 revision으로 downgrade
cd api && uv run alembic downgrade <revision>

# 현재 상태 확인
cd api && uv run alembic current

# 마이그레이션 이력 확인
cd api && uv run alembic history
```

### 회귀 테스트 선행 권장

```bash
uv --project api run pytest api/tests/integration/test_migrations.py -v
```

---

## §7. 환경변수 목록 + 발급처

`.env.example` 기준 전수 목록 (2026-04-24):

| 변수명 | 용도 | 발급처 |
|---|---|---|
| `DATABASE_URL` | PostgreSQL async URL (psycopg) | 자체 구성 |
| `DATABASE_SYNC_URL` | PostgreSQL sync URL (Alembic) | 자체 구성 |
| `REDIS_URL` | Redis 연결 URL (DB 0~4 고정 용도) | 자체 구성 |
| `DENVIA_JWT_SECRET` | JWT 서명 비밀키 (최소 32자) | 자체 생성 |
| `DENVIA_JWT_ALGORITHM` | JWT 알고리즘 (기본: HS256) | 자체 구성 |
| `DENVIA_ADMIN_EMAIL` | 관리자 초기 계정 이메일 | 자체 구성 |
| `DENVIA_ADMIN_INITIAL_PASSWORD` | 관리자 초기 비밀번호 | 자체 구성 |
| `SENTRY_DSN_WEB` | Next.js Sentry DSN | Sentry (sentry.io) |
| `SENTRY_DSN_API` | FastAPI Sentry DSN | Sentry (sentry.io) |
| `SENTRY_ENVIRONMENT` | Sentry 환경 태그 | 자체 구성 |
| `OPENAI_API_KEY` | OpenAI API 키 (RAG용) | OpenAI Platform |
| `KAKAO_CLIENT_ID` | Kakao OAuth 앱 키 | Kakao Developers |
| `KAKAO_CLIENT_SECRET` | Kakao OAuth 시크릿 | Kakao Developers |
| `KAKAO_REDIRECT_URI` | Kakao OAuth 콜백 URI | 자체 구성 |
| `GOOGLE_CLIENT_ID` | Google OAuth 클라이언트 ID | Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | Google OAuth 시크릿 | Google Cloud Console |
| `GOOGLE_REDIRECT_URI` | Google OAuth 콜백 URI | 자체 구성 |
| `NAVER_CLIENT_ID` | Naver OAuth 클라이언트 ID | Naver Developers |
| `NAVER_CLIENT_SECRET` | Naver OAuth 시크릿 | Naver Developers |
| `NAVER_REDIRECT_URI` | Naver OAuth 콜백 URI | 자체 구성 |
| `OAUTH_WEB_ORIGIN` | OAuth 허용 웹 오리진 | 자체 구성 |

**예고 항목 (미정의, `.env.example` 주석)**:
- `MESSAGING_PROVIDER` — Story 4.1에서 stub → 실벤더 교체 시 추가
- `PG_PROVIDER` — Story 3.1, `PG_PROVIDER=toss` 확정 (HOLD-PG 해제 후 활성화)

⚠️ **`.env.example` 미정의 항목** (Story 9.4 ONBOARDING §1.3과 동일 경고):
- `ALIMTALK_TEMPLATE_MAP_JSON` — 알림톡 템플릿 매핑 JSON. Story 4.1에서 정의 예정.
- `BILLING_KEY_ENCRYPTION_KEY` — Toss Payments 결제 키 암호화. Story 3.1에서 정의 예정.

ℹ️ 관리자 알림톡 수신처는 환경변수가 아니라 **DB `users.phone`** 에서 직접 조회한다
(`btmdesign@naver.com` → `admin@denvia.ai.kr` 순). 인수 시 관리자 phone 컬럼만 채우면 된다.

---

## §8. 백업·복구 절차

### PostgreSQL 백업

```bash
# 백업 생성
pg_dump -U denvia -F c denvia > backup_$(date +%Y%m%d).dump

# 복구
pg_restore -U denvia -d denvia backup_$(date +%Y%m%d).dump
```

스케줄: `docs/OPERATIONS.md` §2 주간 작업(Story 9.4) 참조.

### FAISS 인덱스 백업

```bash
# FAISS 이중 경로 스왑 파일 tar 백업
# (TBD — Story 2.1에서 api/data/faiss/index_<a|b>/ 생성 후 절차 구체화)
tar -czf faiss_backup_$(date +%Y%m%d).tar.gz api/data/faiss/
```

> **주의**: `api/data/faiss/` 실디렉터리는 Story 2.1에서 생성 예정이다(TBD — Story 2.1 이후).
