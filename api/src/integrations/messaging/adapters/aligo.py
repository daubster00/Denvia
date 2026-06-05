"""Aligo 알림톡·SMS 어댑터 (AR35 해제, 2026-05-07).

알리고 REST API를 호출해 SMS와 카카오 알림톡을 발송한다.

환경변수 (api/src/settings.py):
  - ALIGO_API_KEY, ALIGO_USER_ID, ALIGO_SENDER (SMS 발송 필수)
  - ALIGO_SENDER_KEY, ALIMTALK_TEMPLATE_MAP_JSON (알림톡 발송 필수)
  - ALIGO_TEST_MODE (기본 True — 실제 발송 없이 API 응답만 검증)

알리고 응답 규약:
  - SMS: { "result_code": "1", "message": "success", "msg_id": ... }  → 양수=성공, 음수=실패
  - 알림톡: { "code": 0, "message": "success", "info": { "mid": ... } } → 0/양수=성공, 음수=실패

NotificationService의 tenacity 재시도 루프가 이 어댑터를 감싸므로,
이 모듈은 실패 시 raise만 하고 자체 재시도는 하지 않는다.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

from api.src.integrations.messaging.port import AlimtalkResult
from api.src.integrations.messaging.templates import (
    TemplateButton,
    get_template,
    render_sms_body,
)
from api.src.settings import settings

logger = structlog.get_logger(__name__)

_OTP_BODY_TEMPLATE = "[Denvia] 인증번호: {code}\n3분 안에 입력해주세요."
_SMS_BYTE_LIMIT = 90  # 90바이트 초과 시 LMS로 전환 (알리고 자동 산정도 있으나 명시 전송)

_SMS_PATH = "/send/"
_ALIMTALK_PATH = "/akv10/alimtalk/send/"


class AligoConfigError(RuntimeError):
    """알리고 환경변수 또는 템플릿 매핑이 누락된 경우 발생한다."""


def _mask_phone(phone: str) -> str:
    return "****" + phone[-4:] if len(phone) >= 4 else "****"


def _normalize_phone(phone: str) -> str:
    return phone.replace("-", "").replace(" ", "")


def _serialize_buttons(buttons: list[TemplateButton]) -> str:
    """알리고 button_1 form 필드용 JSON 직렬화."""
    payload = {
        "button": [
            {
                "name": btn.name,
                "linkType": btn.link_type,
                "linkMo": btn.link_mo,
                "linkPc": btn.link_pc,
                "linkIos": btn.link_ios,
                "linkAnd": btn.link_and,
            }
            for btn in buttons
        ]
    }
    return json.dumps(payload, ensure_ascii=False)


class AligoMessagingAdapter:
    """Aligo 알림톡·SMS 어댑터 — `MESSAGING_PROVIDER=aligo` 일 때 사용된다."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport
        self._template_map_cache: dict[str, str] | None = None

    # ── 외부 API ───────────────────────────────────────────────────────────

    async def send_sms_otp(self, phone: str, code: str) -> None:
        body = _OTP_BODY_TEMPLATE.format(code=code)
        # WebOTP API: Android Chrome 자동 입력을 위해 본문 끝에 `@<origin> #<code>` 라인 부착.
        # iOS Safari는 본문 어디든 6자리 숫자만 있으면 OS가 인식하므로 별도 처리 불필요.
        if settings.webotp_bound_origin:
            body = f"{body}\n\n@{settings.webotp_bound_origin} #{code}"
        await self._send_sms_request(phone, body, log_event="send_sms_otp")

    async def send_sms(self, phone: str, body: str) -> None:
        await self._send_sms_request(phone, body, log_event="send_sms")

    async def send_alimtalk(
        self,
        recipient_phone: str,
        template_code: str,
        variables: dict[str, str],
    ) -> AlimtalkResult:
        if not settings.aligo_api_key or not settings.aligo_user_id:
            raise AligoConfigError(
                "ALIGO_API_KEY 또는 ALIGO_USER_ID가 설정되지 않았습니다."
            )
        if not settings.aligo_sender_key:
            raise AligoConfigError(
                "ALIGO_SENDER_KEY(알림톡 송신프로필키)가 설정되지 않았습니다."
            )
        if not settings.aligo_sender:
            raise AligoConfigError("ALIGO_SENDER(발신번호)가 설정되지 않았습니다.")

        template = get_template(template_code)
        rendered_body = render_sms_body(template, variables)
        tpl_code = self._lookup_tpl_code(template_code)

        # NOTE(2026-05-28): `subject_1`(강조표기 헤더)을 보내지 않는다.
        # 알리고 콘솔에 등록된 모든 템플릿은 "기본형" — 강조표기 미사용. 기본형
        # 템플릿에 subject_1을 채워 보내면 카카오 비즈채널 검증이 "메시지가
        # 템플릿과 일치하지않음"으로 반려한다(UH_9849 미수신 원인).
        form: dict[str, str] = {
            "apikey": settings.aligo_api_key,
            "userid": settings.aligo_user_id,
            "senderkey": settings.aligo_sender_key,
            "tpl_code": tpl_code,
            "sender": settings.aligo_sender,
            "receiver_1": _normalize_phone(recipient_phone),
            "message_1": rendered_body,
            "testmode_yn": "Y" if settings.aligo_test_mode else "N",
        }

        # 등록된 버튼이 있으면 발송 form에 button_1로 직렬화해 함께 보낸다.
        # 카카오 비즈채널 검증은 등록 버튼이 발송 시 누락되면
        # "메시지가 템플릿과 일치하지 않음"으로 반려한다(UH_9849 A/B 검증 완료, 2026-05-28).
        if template.buttons:
            form["button_1"] = _serialize_buttons(template.buttons)

        async with self._client() as client:
            response = await client.post(
                f"{settings.aligo_alimtalk_base_url}{_ALIMTALK_PATH}",
                data=form,
            )

        payload = self._parse_json(response, "send_alimtalk")
        code_raw = payload.get("code", payload.get("result_code", "-1"))
        try:
            code_int = int(code_raw)
        except (TypeError, ValueError):
            code_int = -1

        success = code_int >= 0 and response.status_code == 200
        info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
        # 알리고는 mid(메시지 ID)를 정수로 내려준다(예: 1363220599). AlimtalkResult·
        # TestSendResponse 계약은 str|None 이므로 경계에서 문자열로 변환한다.
        # (미변환 시 응답 직렬화 단계에서 pydantic ValidationError → 발송 성공인데 HTTP 500)
        mid_raw = info.get("mid") if info else None
        message_id = str(mid_raw) if mid_raw is not None else None

        log_data = {
            "phone": _mask_phone(recipient_phone),
            "template_code": template_code,
            "tpl_code": tpl_code,
            "provider_response_code": str(code_raw),
            "test_mode": settings.aligo_test_mode,
        }
        if success:
            logger.info("messaging.aligo.send_alimtalk.success", **log_data)
        else:
            logger.warning(
                "messaging.aligo.send_alimtalk.fail",
                aligo_message=payload.get("message", ""),
                **log_data,
            )

        return AlimtalkResult(
            success=success,
            provider_response_code=str(code_raw),
            message_id=message_id,
        )

    # ── 내부 ───────────────────────────────────────────────────────────────

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=self._transport,
            timeout=httpx.Timeout(30.0, connect=10.0),
        )

    def _lookup_tpl_code(self, template_code: str) -> str:
        if self._template_map_cache is None:
            try:
                parsed = json.loads(settings.alimtalk_template_map_json or "{}")
            except (TypeError, ValueError) as exc:
                raise AligoConfigError(
                    f"ALIMTALK_TEMPLATE_MAP_JSON 파싱 실패: {exc}"
                ) from exc
            if not isinstance(parsed, dict):
                raise AligoConfigError(
                    "ALIMTALK_TEMPLATE_MAP_JSON 은 JSON 객체여야 합니다."
                )
            self._template_map_cache = {str(k): str(v) for k, v in parsed.items()}

        tpl_code = self._template_map_cache.get(template_code)
        if not tpl_code:
            raise AligoConfigError(
                f"ALIMTALK_TEMPLATE_MAP_JSON에 '{template_code}' 매핑이 없습니다. "
                "알리고 콘솔에 템플릿을 등록하고 환경변수에 tpl_code를 추가하세요."
            )
        return tpl_code

    async def _send_sms_request(
        self,
        phone: str,
        body: str,
        log_event: str,
    ) -> None:
        if not (
            settings.aligo_api_key
            and settings.aligo_user_id
            and settings.aligo_sender
        ):
            raise AligoConfigError(
                "ALIGO_API_KEY / ALIGO_USER_ID / ALIGO_SENDER 중 누락된 값이 있습니다."
            )

        msg_type = "LMS" if len(body.encode("utf-8")) > _SMS_BYTE_LIMIT else "SMS"
        form = {
            "key": settings.aligo_api_key,
            "user_id": settings.aligo_user_id,
            "sender": settings.aligo_sender,
            "receiver": _normalize_phone(phone),
            "msg": body,
            "msg_type": msg_type,
            "testmode_yn": "Y" if settings.aligo_test_mode else "N",
        }

        async with self._client() as client:
            response = await client.post(
                f"{settings.aligo_sms_base_url}{_SMS_PATH}",
                data=form,
            )

        payload = self._parse_json(response, log_event)
        try:
            result_code = int(payload.get("result_code", "-1"))
        except (TypeError, ValueError):
            result_code = -1

        log_data = {
            "phone": _mask_phone(phone),
            "msg_type": msg_type,
            "body_length": len(body),
            "result_code": result_code,
            "test_mode": settings.aligo_test_mode,
        }
        if result_code > 0 and response.status_code == 200:
            logger.info(f"messaging.aligo.{log_event}.success", **log_data)
            return

        message = payload.get("message", "")
        logger.warning(
            f"messaging.aligo.{log_event}.fail",
            aligo_message=message,
            **log_data,
        )
        raise RuntimeError(
            f"Aligo {log_event} 실패: code={result_code} message={message}"
        )

    @staticmethod
    def _parse_json(response: httpx.Response, log_event: str) -> dict[str, Any]:
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error(
                f"messaging.aligo.{log_event}.invalid_json",
                status_code=response.status_code,
            )
            raise RuntimeError(f"Aligo 응답 JSON 파싱 실패: {exc}") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"Aligo 응답이 JSON 객체가 아닙니다: {type(data).__name__}")
        return data
