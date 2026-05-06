"""감사 로그 액션 상수 및 @audit_action 데코레이터 — Story 5.1."""

import functools

from fastapi import Request

# 감사 액션 상수
AUDIT_USER_PERMISSION_EDIT = "user.permission_edit"     # A-202 (Story 5.1/6.2)
AUDIT_USER_BLOCK_AUTO_EXPIRED = "user.block_auto_expired"  # A-202 자동 만료 (Story 6.2)
AUDIT_USER_SPEED_OVERRIDE = "user.speed_override"       # A-203 (Story 6.3) — 응답 속도 단독 변경
AUDIT_USER_WITHDRAW = "user.withdraw"                   # Story 1.7 — 본인 계정 탈퇴
AUDIT_NOTICE_PUBLISH = "notice.publish"                 # A-301
AUDIT_POPUP_CREATE = "popup.create"                     # A-302
AUDIT_POPUP_UPDATE = "popup.update"                     # A-302
AUDIT_POPUP_TOGGLE = "popup.toggle"                     # A-302
AUDIT_POPUP_DELETE = "popup.delete"                     # A-302
AUDIT_RAG_UPLOAD = "rag.upload"                         # A-401
AUDIT_RAG_KNOWLEDGE_EDIT = "rag.knowledge_edit"         # A-402
AUDIT_RAG_KNOWLEDGE_DELETE = "rag.knowledge_delete"     # A-402 삭제
AUDIT_RAG_REBUILD = "rag.rebuild"                       # A-403
AUDIT_PROMPT_EDIT = "prompt.edit"                       # A-404
AUDIT_MODEL_PARAMS_EDIT = "rag.model_params.update"     # A-404 모델 파라미터
AUDIT_KILLSWITCH_TOGGLE = "killswitch.toggle"           # A-502


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
