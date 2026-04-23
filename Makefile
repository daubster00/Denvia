.PHONY: dev migrate seed-admin test logs help

dev: ## 전체 서비스 기동 (개발환경)
	docker compose -f infra/docker-compose.yml up -d

migrate: ## Alembic 마이그레이션 실행
	docker compose -f infra/docker-compose.yml exec api alembic upgrade head

seed-admin: ## 관리자 초기 계정 삽입 (멱등)
	docker compose -f infra/docker-compose.yml exec api python scripts/seed_admin.py

test: ## 전체 테스트 실행
	cd web && pnpm vitest run
	docker compose -f infra/docker-compose.yml exec api pytest

logs: ## 전체 로그 스트리밍
	docker compose -f infra/docker-compose.yml logs -f

help: ## 사용 가능한 명령어 목록
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
