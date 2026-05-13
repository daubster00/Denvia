"""SEO 설정 스키마 — 관리자 설정 → SEO.

브라우저 탭 제목·검색엔진 노출 텍스트·카카오톡/SNS 미리보기 이미지·즐겨찾기 아이콘을
관리자 화면에서 직접 편집한다.

필드:
- site_name        브라우저 탭 제목 + Open Graph 기본 제목
- site_description 검색 결과/공유 미리보기 설명
- keywords         검색엔진 키워드 (쉼표 구분, Pydantic은 문자열로 받고 서비스에서 정리)
- og_image_url     카카오톡/페이스북 공유 시 보이는 1200×630 권장 이미지 URL
- favicon_url      브라우저 탭 옆 작은 아이콘 URL

응답은 default_* 도 같이 돌려준다 → 관리자 화면에서 "기본값으로 초기화" 안내용.
"""

from pydantic import BaseModel, Field


class SeoConfigResponse(BaseModel):
    site_name: str
    site_description: str
    keywords: str
    og_image_url: str
    favicon_url: str
    default_site_name: str
    default_site_description: str
    default_keywords: str
    default_og_image_url: str
    default_favicon_url: str


class SeoConfigUpdateRequest(BaseModel):
    site_name: str = Field(min_length=1, max_length=120)
    site_description: str = Field(min_length=1, max_length=300)
    # keywords 는 빈 문자열 허용 (검색엔진 키워드는 선택사항).
    keywords: str = Field(max_length=300, default="")
    og_image_url: str = Field(min_length=1, max_length=500)
    favicon_url: str = Field(min_length=1, max_length=500)


class SeoAssetUploadResponse(BaseModel):
    """업로드 후 응답 — URL 을 SeoConfigUpdateRequest 의 해당 필드에 넣어 PUT."""

    asset_url: str
    kind: str  # "favicon" | "og_image"
