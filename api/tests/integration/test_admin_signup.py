"""Story 10.2 — 관리자 가입 신청 통합 테스트.

2026-05-27: 휴대폰 OTP 인증 단계가 제거됨. 이름/이메일/연락처/비밀번호만 검증.

검증 범위:
- POST /api/v1/admin/auth/signup — 성공/중복/검증 실패
- POST /api/v1/admin/auth/login — pending 등급 차단(401 ADMIN_PENDING_APPROVAL + 쿠키 미발급)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.utils.argon2 import hash_password


def _make_user(
    *,
    user_id: int = 99,
    email: str = "newadmin@denvia.local",
    role: str = "admin",
    admin_grade: str | None = "pending",
    password: str = "password123",
) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.email = email
    user.role = role
    user.admin_grade = admin_grade
    user.subscription_status = "free"
    user.password_hash = hash_password(password)
    user.withdrawn_at = None
    return user


class TestAdminSignupEndpoint:
    async def test_signup_성공_201_세션_쿠키_미발급(self):
        applicant = _make_user(user_id=42, email="apply@denvia.local")

        async def _fake_signup(**kwargs):
            return applicant

        # 2026-05-28 — 신규 관리자 가입 알림톡(admin.account.signup_request) 발송 폐기.
        # master/operator는 /admin/admins 페이지에서 pending 항목을 직접 확인한다.
        with patch(
            "api.src.routers.admin.auth.signup_admin_pending",
            new=AsyncMock(side_effect=_fake_signup),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.post(
                    "/api/v1/admin/auth/signup",
                    json={
                        "name": "홍길동",
                        "email": "apply@denvia.local",
                        "password": "password123",
                        "phone": "01012345678",
                    },
                )

        assert res.status_code == 201
        body = res.json()
        assert body["user_id"] == 42
        assert body["admin_grade"] == "pending"
        assert "승인 후 로그인" in body["message"]

        # 세션 쿠키가 발급되지 않아야 함
        set_cookie = " ".join(res.headers.get_list("set-cookie"))
        assert "denvia_admin_session=" not in set_cookie

    async def test_signup_이름_누락_422(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/v1/admin/auth/signup",
                json={
                    "email": "apply@denvia.local",
                    "password": "password123",
                    "phone": "01012345678",
                },
            )
        assert res.status_code == 422

    async def test_signup_이름_공백만_422(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/v1/admin/auth/signup",
                json={
                    "name": "   ",
                    "email": "apply@denvia.local",
                    "password": "password123",
                    "phone": "01012345678",
                },
            )
        assert res.status_code == 422

    async def test_signup_비밀번호_8자_미만_422(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/v1/admin/auth/signup",
                json={
                    "name": "홍길동",
                    "email": "apply@denvia.local",
                    "password": "short",
                    "phone": "01012345678",
                },
            )
        assert res.status_code == 422

    async def test_signup_연락처_형식_오류_422(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/v1/admin/auth/signup",
                json={
                    "name": "홍길동",
                    "email": "apply@denvia.local",
                    "password": "password123",
                    "phone": "abc",
                },
            )
        assert res.status_code == 422

    async def test_signup_이메일_중복_409(self):
        from fastapi import HTTPException

        async def _fake_signup(**kwargs):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ACCOUNT_EMAIL_DUPLICATE",
                    "message": "이미 사용 중인 이메일입니다.",
                },
            )

        with patch(
            "api.src.routers.admin.auth.signup_admin_pending",
            new=AsyncMock(side_effect=_fake_signup),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.post(
                    "/api/v1/admin/auth/signup",
                    json={
                        "name": "홍길동",
                        "email": "user@denvia.local",
                        "password": "password123",
                        "phone": "01012345678",
                    },
                )

        assert res.status_code == 409
        assert res.json()["code"] == "ACCOUNT_EMAIL_DUPLICATE"

    async def test_signup_연락처_중복_409(self):
        from fastapi import HTTPException

        async def _fake_signup(**kwargs):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ACCOUNT_PHONE_DUPLICATE",
                    "message": "이미 사용 중인 연락처입니다.",
                },
            )

        with patch(
            "api.src.routers.admin.auth.signup_admin_pending",
            new=AsyncMock(side_effect=_fake_signup),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.post(
                    "/api/v1/admin/auth/signup",
                    json={
                        "name": "홍길동",
                        "email": "apply@denvia.local",
                        "password": "password123",
                        "phone": "01012345678",
                    },
                )

        assert res.status_code == 409
        assert res.json()["code"] == "ACCOUNT_PHONE_DUPLICATE"


class TestAdminLoginPendingBlock:
    async def test_pending_등급_로그인_시도_401_쿠키_미발급(self):
        pending = _make_user(admin_grade="pending")
        with (
            patch(
                "api.src.routers.admin.auth.login_user",
                new=AsyncMock(return_value=pending),
            ),
            # commit/add 작동을 위해 get_session에 in-memory mock 주입
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.post(
                    "/api/v1/admin/auth/login",
                    json={
                        "email": "pending@denvia.local",
                        "password": "password123",
                    },
                )

        assert res.status_code == 401
        assert res.json()["code"] == "ADMIN_PENDING_APPROVAL"

        # 세션 쿠키 미발급 검증
        set_cookie = " ".join(res.headers.get_list("set-cookie"))
        assert "denvia_admin_session=" not in set_cookie or "Max-Age=0" in set_cookie

    async def test_master_등급_로그인_정상_200_쿠키_발급(self):
        master = _make_user(admin_grade="master", email="btmdesign@naver.com")
        with patch(
            "api.src.routers.admin.auth.login_user", new=AsyncMock(return_value=master)
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.post(
                    "/api/v1/admin/auth/login",
                    json={
                        "email": "btmdesign@naver.com",
                        "password": "password123",
                    },
                )
        assert res.status_code == 200
        set_cookie = " ".join(res.headers.get_list("set-cookie"))
        assert "denvia_admin_session=" in set_cookie


class TestAdminSmsEndpointsRemoved:
    """2026-05-27: 관리자 가입에서 휴대폰 OTP 단계가 제거되어 SMS 엔드포인트도 함께 삭제."""

    async def test_admin_sms_send_404(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/v1/admin/auth/sms/send",
                json={"phone": "01012345678", "purpose": "admin_signup"},
            )
        assert res.status_code == 404

    async def test_admin_sms_verify_404(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/v1/admin/auth/sms/verify",
                json={"phone": "01012345678", "code": "123456", "purpose": "admin_signup"},
            )
        assert res.status_code == 404
