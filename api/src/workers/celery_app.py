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
        "api.src.workers.content_schedule_tasks",  # Story 4.2: F-502 야간 차단 토글
        "api.src.workers.forex_tasks",         # Story 5.5 후속: USD→KRW 환율 일일 자동 갱신
        "api.src.workers.career_tasks",        # 연차 매년 1월 1일 +1 자동 가산
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
        # Story 4.2: F-502 야간 광고 차단 상태 전환 — KST 21:00 / 08:00
        # (budget-check-hourly 매시 minute=0과 동시 발화 허용 — 별도 워커 처리, 충돌 없음)
        "toggle-night-block-on-2100": {
            "task": "content_schedule_tasks.toggle_night_block_on",
            "schedule": crontab(hour=21, minute=0),
        },
        "toggle-night-block-off-0800": {
            "task": "content_schedule_tasks.toggle_night_block_off",
            "schedule": crontab(hour=8, minute=0),
        },
        # USD→KRW 환율 자동 갱신 — 매일 09:00 KST 1회 (한국수출입은행 영업일 11:00 게시
        # 이전 호출 시 직전 영업일 데이터로 폴백). 09시는 장 시작 직후이고 분 슬롯이
        # 비어 있어 다른 태스크와 충돌 없음.
        "forex-update-usd-krw-daily-0900": {
            "task": "forex_tasks.update_usd_krw",
            "schedule": crontab(hour=9, minute=0),
        },
        # 연차 자동 +1 가산 — 매년 1월 1일 00:05 KST.
        # 자정 정각이 아닌 5분 뒤로 잡는 이유는 자정 정각 슬롯 충돌 회피 + 시스템 시각
        # 동기화 여유. 멱등 SQL이라 같은 해 두 번 실행돼도 안전.
        "career-annual-increment-jan-1-0005": {
            "task": "career_tasks.annual_increment",
            "schedule": crontab(month_of_year=1, day_of_month=1, hour=0, minute=5),
        },
    },
)
