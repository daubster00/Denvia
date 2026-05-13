"""관리자 설정 → SEO 라우터.

엔드포인트:
- GET    /admin/seo-config           현재 SEO 설정 + 기본값 조회
- PUT    /admin/seo-config           SEO 설정 저장 (감사 로그 INSERT)
- POST   /admin/seo-config/asset-upload?kind={favicon|og_image}  이미지 업로드
"""

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile
from redis.asyncio import Redis as AsyncRedis

from api.src.deps.auth import require_admin
from api.src.deps.redis import get_redis_runtime
from api.src.middleware.audit_actions import (
    AUDIT_SEO_ASSET_UPLOAD,
    AUDIT_SEO_CONFIG_UPDATE,
    audit_action,
)
from api.src.models.user import User
from api.src.schemas.admin.seo import (
    SeoAssetUploadResponse,
    SeoConfigResponse,
    SeoConfigUpdateRequest,
)
from api.src.services import seo_service

router = APIRouter(prefix="/admin", tags=["admin-seo"])


def _to_response(cfg: seo_service.SeoConfig) -> SeoConfigResponse:
    return SeoConfigResponse(
        site_name=cfg.site_name,
        site_description=cfg.site_description,
        keywords=cfg.keywords,
        og_image_url=cfg.og_image_url,
        favicon_url=cfg.favicon_url,
        default_site_name=seo_service.DEFAULT_SITE_NAME,
        default_site_description=seo_service.DEFAULT_SITE_DESCRIPTION,
        default_keywords=seo_service.DEFAULT_KEYWORDS,
        default_og_image_url=seo_service.DEFAULT_OG_IMAGE_URL,
        default_favicon_url=seo_service.DEFAULT_FAVICON_URL,
    )


@router.get("/seo-config", response_model=SeoConfigResponse)
async def get_seo_config(
    response: Response,
    admin: User = Depends(require_admin),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> SeoConfigResponse:
    """현재 SEO 설정 + 기본값 조회 (관리자 전용)."""
    response.headers["Cache-Control"] = "no-store"
    cfg = await seo_service.get_seo_config(redis_runtime)
    return _to_response(cfg)


# ── public 엔드포인트 — Next.js generateMetadata 가 SSR 시점에 호출 ────────────


class _PublicSeoResponse(SeoConfigResponse):
    """public 응답은 default_* 도 동봉(필드 시그니처 유지) — 클라이언트가 무시."""


@router.get("/seo-config/public", response_model=_PublicSeoResponse)
async def get_seo_config_public(
    response: Response,
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> _PublicSeoResponse:
    """SSR generateMetadata 용 비인증 조회. 60초 캐시 가능 (HTML head 갱신용)."""
    response.headers["Cache-Control"] = "public, max-age=60"
    cfg = await seo_service.get_seo_config(redis_runtime)
    return _PublicSeoResponse(
        site_name=cfg.site_name,
        site_description=cfg.site_description,
        keywords=cfg.keywords,
        og_image_url=cfg.og_image_url,
        favicon_url=cfg.favicon_url,
        default_site_name=seo_service.DEFAULT_SITE_NAME,
        default_site_description=seo_service.DEFAULT_SITE_DESCRIPTION,
        default_keywords=seo_service.DEFAULT_KEYWORDS,
        default_og_image_url=seo_service.DEFAULT_OG_IMAGE_URL,
        default_favicon_url=seo_service.DEFAULT_FAVICON_URL,
    )


@router.put("/seo-config", response_model=SeoConfigResponse)
@audit_action(AUDIT_SEO_CONFIG_UPDATE)
async def update_seo_config(
    request: Request,
    body: SeoConfigUpdateRequest,
    admin: User = Depends(require_admin),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> SeoConfigResponse:
    """SEO 설정 저장 — 이미지 URL 화이트리스트 검증 후 Redis 저장."""
    seo_service.validate_asset_url(body.og_image_url)
    seo_service.validate_asset_url(body.favicon_url)

    before = await seo_service.get_seo_config(redis_runtime)
    after = await seo_service.set_seo_config(
        redis_runtime,
        site_name=body.site_name.strip(),
        site_description=body.site_description.strip(),
        keywords=body.keywords.strip(),
        og_image_url=body.og_image_url.strip(),
        favicon_url=body.favicon_url.strip(),
    )

    request.state.audit_target_type = "seo_config"
    request.state.audit_diff = {
        "before": {
            "site_name": before.site_name,
            "site_description": before.site_description,
            "keywords": before.keywords,
            "og_image_url": before.og_image_url,
            "favicon_url": before.favicon_url,
        },
        "after": {
            "site_name": after.site_name,
            "site_description": after.site_description,
            "keywords": after.keywords,
            "og_image_url": after.og_image_url,
            "favicon_url": after.favicon_url,
        },
    }
    return _to_response(after)


@router.post(
    "/seo-config/asset-upload",
    response_model=SeoAssetUploadResponse,
    status_code=201,
)
@audit_action(AUDIT_SEO_ASSET_UPLOAD)
async def upload_seo_asset(
    request: Request,
    kind: str = Query(..., pattern="^(favicon|og_image)$"),
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
) -> SeoAssetUploadResponse:
    """파비콘(.png/.ico/.svg) 또는 OG 이미지(.png/.jpg/.webp) 업로드. 5MB 이하."""
    asset_url = await seo_service.upload_asset(file, kind)

    request.state.audit_target_type = "seo_asset"
    request.state.audit_diff = {
        "after": {
            "kind": kind,
            "asset_url": asset_url,
            "original_name": file.filename,
        }
    }
    return SeoAssetUploadResponse(asset_url=asset_url, kind=kind)
