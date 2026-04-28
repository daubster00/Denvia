# 개발 환경 실행 가이드

> 최종 수정일: 2026-04-27

이 프로젝트의 기본 개발 환경은 Docker Compose로 실행한다. Windows, WSL, Claude Code, Codex가 모두 같은 체크아웃을 수정하고, Docker 컨테이너는 그 체크아웃을 `/workspace`로 직접 마운트한다.

## 한 번에 실행

```bash
docker compose -f infra/docker-compose.yml up --build
```

처음 실행할 때는 프론트 의존성(`pnpm install`)과 백엔드 의존성(`uv sync`)을 컨테이너 안의 Linux 볼륨에 설치하므로 시간이 걸릴 수 있다. 이후에는 코드 수정 시 이미지를 다시 굽지 않아도 된다.

WSL/Codex에서 Docker 명령까지 직접 실행하려면 Docker Desktop의 WSL integration이 현재 WSL 배포판에 켜져 있어야 한다. Docker Desktop에서 `Settings > Resources > WSL Integration`으로 이동해 사용하는 WSL 배포판을 활성화한 뒤 WSL 터미널을 다시 열고 아래 명령이 동작하는지 확인한다.

```bash
docker version
docker compose version
```

## 접속 주소

| 서비스 | 주소 |
|---|---|
| 프론트엔드 | http://localhost:3000 |
| 백엔드 API | http://localhost:8000 |
| Postgres | localhost:5432 |
| Redis | localhost:6379 |

## 경로 구조

| 보는 주체 | 경로 |
|---|---|
| Windows | `D:\projects\Dental Chatbot` |
| WSL/Codex | `/mnt/d/projects/Dental Chatbot` |
| Docker 컨테이너 | `/workspace` |

세 경로는 같은 프로젝트 폴더를 가리킨다. 예를 들어 WSL에서 `/mnt/d/projects/Dental Chatbot/web/src/...`를 수정하면, Docker의 `/workspace/web/src/...`에도 같은 변경이 즉시 보인다.

## Hot Reload 기준

- 프론트엔드: `next dev`로 실행되며 `/workspace/web` 변경을 즉시 반영한다.
- 백엔드: `uvicorn --reload`로 실행되며 `/workspace/api` 변경 시 자동 재시작한다.
- `vendor/`와 `api/data/faiss/current`도 같은 `/workspace` 아래에서 보이므로 RAG 경로가 Windows/WSL 차이에 덜 흔들린다.
- Celery worker/beat는 장기 실행 프로세스라 코드 변경 후 재시작이 필요할 수 있다.

## 볼륨을 분리한 이유

`node_modules`, `.next`, `.venv`는 Windows 파일과 Linux 파일이 섞이면 깨지기 쉽다. 그래서 compose는 아래 경로를 Docker named volume으로 분리한다.

```text
/workspace/node_modules
/workspace/web/node_modules
/workspace/web/.next
/workspace/api/.venv
```

소스 코드는 로컬 파일을 그대로 쓰고, OS별 의존성/빌드 산출물만 Docker 안에 둔다.

## 자주 쓰는 명령

```bash
# 전체 실행
docker compose -f infra/docker-compose.yml up

# 백그라운드 실행
docker compose -f infra/docker-compose.yml up -d

# 로그 보기
docker compose -f infra/docker-compose.yml logs -f web api

# 종료
docker compose -f infra/docker-compose.yml down

# 의존성 볼륨까지 초기화가 필요할 때만 사용
docker compose -f infra/docker-compose.yml down -v
```

`down -v`는 Postgres 데이터와 의존성 볼륨을 함께 지울 수 있으므로, DB 데이터를 보존해야 하면 사용하지 않는다.
