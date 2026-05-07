"""Celery 앱 설정 — Redis를 broker/result backend로 사용한다."""

from celery import Celery
from celery.schedules import crontab

import api.src.models  # noqa: F401 — 워커 시작 시 모든 ORM 모델을 메타데이터에 등록
from api.src.settings import REDIS_DB_CELERY, settings

# Redis DB 0: Celery broker/result
broker_url = f"{settings.redis_url}/{REDIS_DB_CELERY}"
result_backend = f"{settings.redis_url}/{REDIS_DB_CELERY}"

celery_app = Celery(
    "denvia",
    broker=broker_url,
    backend=result_backend,
    include=[
        "api.src.workers.notification_tasks",  # Story 4.1: 알림 큐 태스크
        "api.src.workers.retention_tasks",     # Story 5.1: 감사 로그 retention
        "api.src.workers.rag_tasks",           # Story 8.3: RAG 재빌드
        "api.src.workers.budget_tasks",        # Story 5.2: 예산 임계 감시
        "api.src.workers.billing_tasks",       # Story 3.3: 자동 갱신 배치
        "api.src.workers.anomaly_tasks",       # Story 6.2: 차단 자동 만료
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=True,
    beat_schedule={
        # 큐 대기 항목 처리 (Epic 3 billing 이벤트 backlog) — 5분마다
        "dispatch-queued-every-5min": {
            "task": "notification_tasks.dispatch_queued",
            "schedule": 300,  # 5분 (초)
        },
        # 야간 차단 해제 후 deferred 항목 발송 — 매일 08:05 KST
        "dispatch-deferred-daily-0805": {
            "task": "notification_tasks.dispatch_deferred",
            "schedule": crontab(hour=8, minute=5),  # KST 08:05 (timezone="Asia/Seoul")
        },
        # rate_limited_deferred 재처리 — 매 시간 5분
        "dispatch-deferred-hourly": {
            "task": "notification_tasks.dispatch_deferred",
            "schedule": crontab(minute=5),
        },
        # audit_logs 1년 이상 레코드 삭제 — 매일 03:00 KST (NFR-S7)
        "retention-audit-logs-daily": {
            "task": "retention_tasks.delete_old_audit_logs",
            "schedule": crontab(hour=3, minute=0),
        },
        # Story 8.3: 4h 이상 running 상태 재빌드 job 실패 처리 — 10분마다
        "reap-stale-rebuilds-10min": {
            "task": "rag.reap_stale_rebuilds",
            "schedule": 600,
        },
        # Story 8.3: 소프트 삭제 파일 30일 후 FS 영구 삭제 — 매일 04:00 KST
        "purge-deleted-knowledge-daily": {
            "task": "rag.purge_deleted_knowledge_files",
            "schedule": crontab(hour=4, minute=0),
        },
        # Story 5.2: 예산 임계 감시 + auto kill-switch — 매시 정각 KST
        "budget-check-hourly": {
            "task": "budget_tasks.check_thresholds",
            "schedule": crontab(minute=0),
        },
        # Story 3.3: 월 자동 갱신 스캔 — 매일 04:00 KST
        "auto-renew-scan-daily-0400": {
            "task": "billing.auto_renew_scan",
            "schedule": crontab(hour=4, minute=0),
        },
        # Story 3.5: 매시 15분 — cancel_pending && current_period_end<=now 일괄 종료
        # (budget-check-hourly가 minute=0을 점유 중이므로 분 슬롯 분산)
        "finalize-cancellations-hourly-15": {
            "task": "billing.finalize_cancellations",
            "schedule": crontab(minute=15),
        },
        # Story 6.2: 매시 30분 — 만료된 수동 차단 자동 해제
        # (분 슬롯 분산: 0=budget, 5=deferred, 15=finalize, 30=expire-blocks)
        "expire-blocks-hourly-30": {
            "task": "anomaly_tasks.expire_blocks",
            "schedule": crontab(minute=30),
        },
        # Story 9.1: payments + payment_events 5년 retention — 매일 03:30 KST
        # (audit-logs 03:00과 분리해 시간/분 슬롯 충돌 회피)
        "retention-payments-daily": {
            "task": "retention_tasks.delete_old_payments",
            "schedule": crontab(hour=3, minute=30),
        },
    },
)
