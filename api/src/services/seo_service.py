"""SEO 설정 서비스 — Redis DB 3 게이트웨이 + 정적 자산 업로드.

관리자 설정 → SEO 페이지의 백엔드. 브라우저 탭 제목·검색 미리보기 설명·키워드·
SNS 공유 이미지(OG)·파비콘을 Redis 에 저장하고, 이미지는 디스크에 저장해
``/static/seo-assets/{filename}`` URL 로 노출한다.

설계 메모:
- popup_service.upload_popup_image 패턴을 그대로 답습 — uuid prefix·MIME 화이트리스트·5MB 제한.
- 파비콘은 .ico 도 허용 (브라우저 호환). OG 이미지는 PNG/JPG/WEBP.
- 기본값(default_*) 은 layout.tsx 의 기존 하드코딩 값과 일치시켜 신규 환경에서도 안전 폴백.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import structlog
from fastapi import HTTPException, UploadFile
from redis.asyncio import Redis as AsyncRedis

logger = structlog.get_logger()


# ── Redis 키 (runtime_config 네임스페이스 답습) ────────────────────────────────
KEY_SITE_NAME = "runtime:seo:site_name"
KEY_SITE_DESCRIPTION = "runtime:seo:site_description"
KEY_KEYWORDS = "runtime:seo:keywords"
KEY_OG_IMAGE_URL = "runtime:seo:og_image_url"
KEY_FAVICON_URL = "runtime:seo:favicon_url"

# ── 기본값 — web/src/app/layout.tsx 하드코딩과 일치 ────────────────────────────
DEFAULT_SITE_NAME = "Denvia — 치과 보험청구 AI 어시스턴트"
DEFAULT_SITE_DESCRIPTION = (
    "데스크 행정업무 및 치과 보험청구에 관한 정보를 제공하는 치과 전용 AI 챗봇입니다."
)
DEFAULT_KEYWORDS = ""  # 기존 layout.tsx 에 keywords 없음 — 빈 문자열로 초기화.
DEFAULT_OG_IMAGE_URL = "/og-image.png"
DEFAULT_FAVICON_URL = "/favicon.png"


@dataclass(frozen=True)
class SeoConfig:
    site_name: str
    site_description: str
    keywords: str
    og_image_url: str
    favicon_url: str


# ── 정적 자산 업로드 (popup_service 패턴 답습) ────────────────────────────────
SEO_ASSET_DIR = (
    Path(__file__).parent.parent.parent / "data" / "uploads" / "seo_assets"
)
SEO_ASSET_URL_PREFIX = "/static/seo-assets"

_OG_ALLOWED_MIMES = {"image/png", "image/jpeg", "image/webp"}
_OG_ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
# 파비콘은 .ico 도 허용 — 일부 구형 브라우저 호환.
_FAVICON_ALLOWED_MIMES = {
    "image/png",
    "image/x-icon",
    "image/vnd.microsoft.icon",
    "image/svg+xml",
}
_FAVICON_ALLOWED_EXTS = {".png", ".ico", ".svg"}
_MAX_ASSET_SIZE_BYTES = 5 * 1024 * 1024  # 5MB — OG/파비콘 모두 충분.


async def get_seo_config(redis_runtime: AsyncRedis) -> SeoConfig:
    """현재 SEO 설정 조회 — 미설정 키는 기본값으로 폴백."""

    site_name = await redis_runtime.get(KEY_SITE_NAME)
    site_description = await redis_runtime.get(KEY_SITE_DESCRIPTION)
    keywords = await redis_runtime.get(KEY_KEYWORDS)
    og_image_url = await redis_runtime.get(KEY_OG_IMAGE_URL)
    favicon_url = await redis_runtime.get(KEY_FAVICON_URL)

    return SeoConfig(
        site_name=str(site_name) if site_name else DEFAULT_SITE_NAME,
        site_description=(
            str(site_description) if site_description else DEFAULT_SITE_DESCRIPTION
        ),
        keywords=str(keywords) if keywords is not None else DEFAULT_KEYWORDS,
        og_image_url=str(og_image_url) if og_image_url else DEFAULT_OG_IMAGE_URL,
        favicon_url=str(favicon_url) if favicon_url else DEFAULT_FAVICON_URL,
    )


async def set_seo_config(
    redis_runtime: AsyncRedis,
    *,
    site_name: str,
    site_description: str,
    keywords: str,
    og_image_url: str,
    favicon_url: str,
) -> SeoConfig:
    """SEO 설정 저장. 라우터에서 화이트리스트·길이 검증 후 호출."""

    await redis_runtime.set(KEY_SITE_NAME, site_name)
    await redis_runtime.set(KEY_SITE_DESCRIPTION, site_description)
    await redis_runtime.set(KEY_KEYWORDS, keywords)
    await redis_runtime.set(KEY_OG_IMAGE_URL, og_image_url)
    await redis_runtime.set(KEY_FAVICON_URL, favicon_url)

    return SeoConfig(
        site_name=site_name,
        site_description=site_description,
        keywords=keywords,
        og_image_url=og_image_url,
        favicon_url=favicon_url,
    )


def validate_asset_url(value: str) -> None:
    """저장 요청에 들어온 og/favicon URL 화이트리스트 검증.

    허용:
    - 업로드된 자산 경로 (/static/seo-assets/...): 본 서비스에서 발급.
    - 기존 정적 자산 (/favicon.png, /og-image.png, /apple-icon.png): 초기 기본값.
    - 외부 URL (http://, https://): 운영자가 CDN 에 호스팅한 이미지 사용 가능.

    차단: 그 외 경로 입력 (file://, javascript:, /../..) — XSS·열거·경로 조작.
    """
    v = (value or "").strip()
    if not v:
        raise HTTPException(
            422,
            detail={
                "code": "SEO_ASSET_URL_REQUIRED",
                "message": "이미지 주소를 입력해주세요.",
            },
        )

    # 외부 URL 허용 (운영자가 CDN 사용 가능).
    if v.startswith("http://") or v.startswith("https://"):
        return

    # 업로드된 자산.
    if v.startswith(SEO_ASSET_URL_PREFIX + "/"):
        rel = v[len(SEO_ASSET_URL_PREFIX) + 1 :]
        if "/" in rel or ".." in rel:
            raise HTTPException(
                422,
                detail={
                    "code": "SEO_ASSET_URL_INVALID",
                    "message": "잘못된 이미지 경로입니다.",
                },
            )
        return

    # 신규 환경 초기 기본값.
    if v in ("/favicon.png", "/apple-icon.png", "/og-image.png"):
        return

    raise HTTPException(
        422,
        detail={
            "code": "SEO_ASSET_URL_INVALID",
            "message": "이미지 주소는 업로드된 파일 또는 http(s):// 주소만 허용됩니다.",
        },
    )


async def upload_asset(
    file: UploadFile,
    kind: str,
) -> str:
    """파비콘 또는 OG 이미지 업로드. 반환값은 /static/seo-assets/{filename} URL.

    kind:
    - "favicon": PNG/ICO/SVG, 5MB 이하
    - "og_image": PNG/JPG/WEBP, 5MB 이하
    """
    if kind not in ("favicon", "og_image"):
        raise HTTPException(
            400,
            detail={
                "code": "SEO_ASSET_KIND_INVALID",
                "message": "지원하지 않는 이미지 종류입니다.",
            },
        )

    allowed_mimes = (
        _FAVICON_ALLOWED_MIMES if kind == "favicon" else _OG_ALLOWED_MIMES
    )
    allowed_exts = (
        _FAVICON_ALLOWED_EXTS if kind == "favicon" else _OG_ALLOWED_EXTS
    )

    if file.content_type not in allowed_mimes:
        msg = (
            "파비콘은 PNG·ICO·SVG 파일만 업로드할 수 있습니다."
            if kind == "favicon"
            else "OG 이미지는 PNG·JPG·WEBP 파일만 업로드할 수 있습니다."
        )
        raise HTTPException(
            422,
            detail={"code": "SEO_ASSET_MIME_INVALID", "message": msg},
        )

    raw_name = file.filename or ""
    ext = Path(raw_name).suffix.lower()
    if ext not in allowed_exts:
        raise HTTPException(
            422,
            detail={
                "code": "SEO_ASSET_EXT_INVALID",
                "message": "허용된 확장자가 아닙니다.",
            },
        )

    contents = await file.read()
    size = len(contents)
    if size > _MAX_ASSET_SIZE_BYTES:
        raise HTTPException(
            422,
            detail={
                "code": "SEO_ASSET_TOO_LARGE",
                "message": "이미지 크기는 5MB 이하여야 합니다.",
            },
        )

    SEO_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    safe_filename = f"{kind}-{uuid.uuid4().hex}{ext}"
    dest = SEO_ASSET_DIR / safe_filename
    dest.write_bytes(contents)

    asset_url = f"{SEO_ASSET_URL_PREFIX}/{safe_filename}"
    logger.info(
        "admin.seo.asset.uploaded",
        kind=kind,
        filename=safe_filename,
        size_bytes=size,
    )
    return asset_url


__all__ = [
    "SeoConfig",
    "get_seo_config",
    "set_seo_config",
    "validate_asset_url",
    "upload_asset",
    "SEO_ASSET_DIR",
    "SEO_ASSET_URL_PREFIX",
    "DEFAULT_SITE_NAME",
    "DEFAULT_SITE_DESCRIPTION",
    "DEFAULT_KEYWORDS",
    "DEFAULT_OG_IMAGE_URL",
    "DEFAULT_FAVICON_URL",
]
