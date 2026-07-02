"""QA 관련 워커 태스크 — 게시판 #112 고아 정리(reaper).

- reap_stuck_qa_logs: qa_logs 가 'in_progress' 상태로 일정 시간 이상 멈춰 있으면
  'error' 로 정리한다 — 5분마다.

배경(#112): 질의응답 스트림은 시작 시 status='in_progress' 로 INSERT 되고, 종료 시
반드시 completed/aborted/error 중 하나로 UPDATE 된다. 그런데 RAG/LLM 생성이 취소
불가능한 백그라운드 스레드에서 돌기 때문에, 긴 생성 도중 클라이언트 단절·프록시
타임아웃·컨테이너 재기동이 겹치면 종료 UPDATE 가 실행되지 못하고 행이 'in_progress'
로 영구히 남는다(관리자 통계에서 '미응답'으로 보임). 이 리퍼가 그런 고아를 정리한다.

임계값은 STUCK_THRESHOLD_MINUTES. 정상 답변은 수십 초 내 완료되므로(관측 최대 latency
~14초) 5분 임계는 오탐 위험이 사실상 없다. LLM 타임아웃(client.LLM_REQUEST_TIMEOUT_SECONDS,
재시도 포함 최악 ~3분)으로 정상 종료되는 경우를 다 흡수하고도 남는 여유값.
"""

import asyncio

import structlog
from sqlalchemy import text

from api.src.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)

# in_progress 로 이 시간 이상 멈춰 있으면 고아로 간주하고 error 로 정리한다.
STUCK_THRESHOLD_MINUTES = 5


@celery_app.task(name="qa_tasks.reap_stuck_qa_logs", bind=True)
def reap_stuck_qa_logs(self) -> dict:
    """5분 넘게 'in_progress' 인 qa_logs 를 'error' 로 정리 — 5분마다."""
    return asyncio.run(_reap_stuck_qa_logs_async())


async def _reap_stuck_qa_logs_async() -> dict:
    from api.src.models.base import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(
            text(
                "UPDATE qa_logs SET status='error' "
                "WHERE status='in_progress' "
                f"AND created_at < NOW() - INTERVAL '{STUCK_THRESHOLD_MINUTES} minutes'"
            )
        )
        await session.commit()
        reaped = result.rowcount

    logger.info("qa_tasks.reap_stuck_qa_logs.done", reaped=reaped)
    return {"reaped": reaped}
