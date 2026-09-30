"""질의응답 실패가 짧은 시간에 몰릴 때 관리자에게 알림톡으로 먼저 알린다.

## 왜 만들었나 (2026-09-30 장애)

14:11~14:35 KST 25분 동안 질문 17건 중 8건이 첫 토큰 45초 상한에 걸려 **빈 화면으로
끝났다.** 그런데 우리는 **고객이 알려 줄 때까지 몰랐다.** 서버는 한가했고(CPU 0.27%)
설정도 그대로였으며 로그에도 경고 한 줄(`qa.stream.first_token_timeout`)만 조용히
쌓였다 — 아무도 보지 않는 곳이다.

그래서 실패가 몰리면 관리자 휴대폰으로 먼저 알린다. 한 건 실패는 늘 있을 수 있으니
**10분 안에 3건 이상**일 때만 울리고, 같은 10분 구간에는 **한 번만** 보낸다
(장애가 30분 이어져도 알림톡은 최대 3통).

## 왜 전용 템플릿을 새로 만들지 않았나

알림톡은 알리고 콘솔에 등록된 템플릿과 **1:1 로 일치**해야 발송된다. 코드에만 추가하면
운영에서 "매핑 없음"으로 실패한다(`[[project_prod_env_map_drift]]` 의 옛 사고).
이미 등록·매핑된 ``admin.anomaly_detected``(UH_9849)는 변수 영역이 자유 문구라
그대로 쓸 수 있어 재사용한다. 전용 템플릿이 필요하면 콘솔 등록 후 분리하면 된다.

## 실패해도 질문 처리를 막지 않는다

알림은 best-effort 다. 수신자 조회·INSERT 가 실패해도 예외를 밖으로 내보내지 않는다.
요청 세션과 분리된 별도 세션을 쓰는 이유도 같다 — 여기서 난 오류가 질의응답 트랜잭션을
오염시키면 안 된다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import insert as pg_insert

logger = structlog.get_logger(__name__)

# 몇 분을 한 묶음으로 보는가. 알림 중복 차단(멱등 키)도 이 길이로 자른다.
ALERT_WINDOW_MINUTES = 10
# 이 건수 이상이면 알린다. 1~2건은 평소에도 나올 수 있어 울리지 않는다.
ALERT_THRESHOLD = 3

# 알림톡 본문 "이상탐지 계정" 자리. 특정 계정 문제가 아니라 서비스 전체 상태다.
_TARGET_LABEL = "서비스 전체"


def _window_bucket(now: datetime) -> str:
    """현재 시각을 ``ALERT_WINDOW_MINUTES`` 단위로 내림한 문자열.

    같은 구간에서는 같은 값이 나오므로, 멱등 키로 쓰면 구간당 1통만 나간다.
    """
    floored = (now.minute // ALERT_WINDOW_MINUTES) * ALERT_WINDOW_MINUTES
    return now.strftime(f"%Y%m%d%H{floored:02d}")


async def maybe_alert_admin_qa_failures(*, qa_log_id: int) -> None:
    """방금 실패한 질문을 계기로 최근 실패가 몰렸는지 보고, 필요하면 알림톡을 예약한다.

    호출 위치: ``QAService.stream`` 의 실패 처리 직후(해당 행을 status='error' 로
    커밋한 **뒤**). 방금 실패한 건도 집계에 포함돼야 하기 때문이다.

    실제 발송은 Celery ``dispatch_queued``(5분 간격)가 맡는다. 여기서는
    ``notification_queue`` 에 status='queued' 로 넣기만 한다.
    """
    from api.src.integrations.messaging.admin_recipient import resolve_admin_target
    from api.src.models.base import async_session_factory
    from api.src.models.notification_queue import (
        CHANNEL_ALIMTALK,
        STATUS_QUEUED,
        NotificationQueue,
    )

    try:
        async with async_session_factory() as session:
            row = await session.execute(
                sql_text(
                    "SELECT count(*) FROM qa_logs "
                    "WHERE status = 'error' "
                    "AND created_at >= now() - make_interval(mins => :mins)"
                ),
                {"mins": ALERT_WINDOW_MINUTES},
            )
            recent_failures = int(row.scalar() or 0)

            if recent_failures < ALERT_THRESHOLD:
                logger.debug(
                    "qa.failure_burst.below_threshold",
                    qa_log_id=qa_log_id,
                    recent_failures=recent_failures,
                    threshold=ALERT_THRESHOLD,
                )
                return

            admin, admin_phone = await resolve_admin_target(session)
            if admin is None or not admin_phone:
                # 관리자 휴대폰이 비어 있으면 조용히 건너뛴다
                # ([[project_admin_alimtalk_recipient_fixed_two]] 와 같은 규칙).
                logger.info(
                    "qa.failure_burst.skip_no_admin_phone",
                    qa_log_id=qa_log_id,
                    recent_failures=recent_failures,
                )
                return

            now_dt = datetime.now(tz=timezone.utc).replace(tzinfo=None)
            bucket = _window_bucket(now_dt)
            stmt = (
                pg_insert(NotificationQueue)
                .values(
                    user_id=admin.id,
                    template_code="admin.anomaly_detected",
                    variables={
                        "anomaly_type": (
                            f"AI 답변 지연·실패 {recent_failures}건"
                            f" (최근 {ALERT_WINDOW_MINUTES}분)"
                        ),
                        "user_identifier": _TARGET_LABEL,
                    },
                    channel=CHANNEL_ALIMTALK,
                    status=STATUS_QUEUED,
                    attempts=0,
                    idempotency_key=f"qa_failure_burst:{bucket}",
                    created_at=now_dt,
                )
                .on_conflict_do_nothing(
                    index_elements=["user_id", "template_code", "idempotency_key"],
                    index_where=NotificationQueue.user_id.is_not(None),
                )
            )
            result = await session.execute(stmt)
            await session.commit()

            logger.warning(
                "qa.failure_burst.admin_alert",
                qa_log_id=qa_log_id,
                recent_failures=recent_failures,
                window_minutes=ALERT_WINDOW_MINUTES,
                bucket=bucket,
                admin_user_id=admin.id,
                # 0 이면 같은 구간에서 이미 보낸 것 — 중복 차단이 동작한 정상 경로다.
                enqueued=bool(result.rowcount),
            )
    except Exception:
        # 알림 실패가 질의응답을 막으면 안 된다. 기록만 남기고 삼킨다.
        logger.error(
            "qa.failure_burst.alert_failed", qa_log_id=qa_log_id, exc_info=True
        )


__all__ = [
    "ALERT_THRESHOLD",
    "ALERT_WINDOW_MINUTES",
    "maybe_alert_admin_qa_failures",
]
