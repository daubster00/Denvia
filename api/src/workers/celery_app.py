"""Celery 앱 설정 — Redis를 broker/result backend로 사용한다."""

from celery import Celery
from celery.schedules import crontab

from api.src.settings import REDIS_DB_CELERY, settings

# Redis DB 0: Celery broker/result
broker_url = f"{settings.redis_url}/{REDIS_DB_CELERY}"
result_backend = f"{settings.redis_url}/{REDIS_DB_CELERY}"

celery_app = Celery(
    "denvia",
    broker=broker_url,
    backend=result_backend,
    include=[
        "api.src.workers.tasks",
        "api.src.workers.notification_tasks",  # Story 4.1: 알림 큐 태스크
        "api.src.workers.retention_tasks",     # Story 5.1: 감사 로그 retention
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
    },
)
