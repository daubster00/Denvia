"""감사 로그 액션 상수 및 @audit_action 데코레이터 — Story 5.1."""

import functools

from fastapi import Request

# 감사 액션 상수
AUDIT_USER_PERMISSION_EDIT = "user.permission_edit"     # A-202 (Story 5.1/6.2)
AUDIT_USER_BLOCK_AUTO_EXPIRED = "user.block_auto_expired"  # A-202 자동 만료 (Story 6.2)
AUDIT_USER_SPEED_OVERRIDE = "user.speed_override"       # A-203 (Story 6.3) — 응답 속도 단독 변경
AUDIT_USER_WITHDRAW = "user.withdraw"                   # Story 1.7 — 본인 계정 탈퇴
AUDIT_NOTICE_PUBLISH = "notice.publish"                 # A-301
AUDIT_NOTICE_CREATE = "notice.create"                   # Story 7.1 — 작성+즉시발행
AUDIT_NOTICE_DELETE = "notice.delete"                   # Story 7.1 — 발행 회수(CASCADE)
AUDIT_INBOX_PREVIEW_CONFIG_UPDATE = "inbox_preview_config.update"  # 노출 개수 전역 설정
AUDIT_POPUP_CREATE = "popup.create"                     # A-302
AUDIT_POPUP_UPDATE = "popup.update"                     # A-302
AUDIT_POPUP_TOGGLE = "popup.toggle"                     # A-302
AUDIT_POPUP_DELETE = "popup.delete"                     # A-302
AUDIT_POPUP_IMAGE_UPLOAD = "popup.image_upload"         # Story 7.2 v2 — 이미지 업로드
AUDIT_SUPPORT_REPLY = "support.reply"                   # Story 9.3 — 관리자 문의 답변/상태 변경
AUDIT_SUPPORT_REPLY_EDIT = "support.reply_edit"         # 관리자 답변 수정 (inquiry_replies + 매칭 inbox 본문 동기 갱신)
AUDIT_SUPPORT_REPLY_DELETE = "support.reply_delete"     # 관리자 답변 삭제 (inquiry_replies + 매칭 inbox row 동기 삭제)
AUDIT_SUPPORT_REPLY_IMAGE_UPLOAD = "support.reply_image_upload"  # 관리자 CS 답변 본문 에디터 이미지 업로드
AUDIT_REFUND_MANUAL_APPROVE = "refund.manual.approve"   # Story 9.3 — 수동 환불 승인 (PG refund 호출 + 9 테이블 전이)
AUDIT_REFUND_MANUAL_DENY = "refund.manual.deny"         # Story 9.3 — 수동 환불 거부 (payment 원복 + 알림)
AUDIT_REFUND_OPERATIONAL_CREATE = "refund.operational.create"  # Story 9.1 v1.1 — 관리자 운영 환불(부분/전액) 실행 (ADR-0001 편차 #5)
AUDIT_RAG_UPLOAD = "rag.upload"                         # A-401
AUDIT_RAG_KNOWLEDGE_EDIT = "rag.knowledge_edit"         # A-402
AUDIT_RAG_KNOWLEDGE_DELETE = "rag.knowledge_delete"     # A-402 삭제
AUDIT_RAG_REBUILD = "rag.rebuild"                       # A-403
AUDIT_PROMPT_EDIT = "prompt.edit"                       # A-404
AUDIT_MODEL_PARAMS_EDIT = "rag.model_params.update"     # A-404 모델 파라미터
AUDIT_SYNONYM_EDIT = "rag.synonym.edit"                 # Story 8.5 — 동의어 그룹 추가/수정/삭제/일괄 가져오기 단일 액션
AUDIT_SYNONYM_EXPORT = "rag.synonym.export"             # Story 8.5 — CSV 내보내기 (선택적 감사)
AUDIT_KILLSWITCH_TOGGLE = "killswitch.toggle"           # A-502 (legacy, 호환성 유지)
AUDIT_KILLSWITCH_MANUAL_TOTAL_ACTIVATE = "killswitch.manual_total.activate"   # Story 9.2 — 수동 비상 정지 발동
AUDIT_KILLSWITCH_MANUAL_TOTAL_DEACTIVATE = "killswitch.manual_total.deactivate"  # Story 9.2 — 수동 비상 정지 해제
AUDIT_ANOMALY_REVIEW = "anomaly.review"                 # Story 6.5 — 이상 이벤트 검토 처리
AUDIT_ANOMALY_THROTTLE_CONFIG_UPDATE = "anomaly_throttle_config.update"  # 이상 질문 패턴 throttle 설정 편집
AUDIT_ANOMALY_THROTTLE_CLEAR = "user.anomaly_throttle_clear"  # 사용자 throttle 수동 해제
AUDIT_RUNTIME_CONFIG_UPDATE = "runtime_config.update"   # A-303/A-305 (Story 7.3/7.4 부분) — 서비스 전체 토글 편집
AUDIT_BUDGET_LIMIT_UPDATE = "budget.monthly_limit.update"  # 관리자 설정 — 당월 KST 예산 한도 조정
AUDIT_SEO_CONFIG_UPDATE = "seo_config.update"           # 관리자 설정 → SEO — 사이트 이름/설명/키워드/OG/파비콘 편집
AUDIT_SEO_ASSET_UPLOAD = "seo_config.asset_upload"      # 관리자 설정 → SEO — 파비콘/OG 이미지 업로드


def audit_action(action: str):
    """FastAPI route에 부착해 request.state.audit_action을 설정한다.

    사용 시 route 함수에 `request: Request` 파라미터가 반드시 있어야 한다.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            req: Request | None = kwargs.get("request")
            if req is not None:
                req.state.audit_action = action
            return await func(*args, **kwargs)
        return wrapper
    return decorator
