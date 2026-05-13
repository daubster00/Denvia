"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchSeoConfig,
  updateSeoConfig,
  uploadSeoAsset,
  type SeoConfig,
} from "@/features/admin-dashboard/api/seo";
import styles from "./page.module.css";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// 백엔드에 저장된 URL 을 미리보기용 절대 URL 로 변환.
//  - http(s)://  → 그대로
//  - /static/... → 백엔드 호스트 prefix
//  - /favicon.png 등 Next.js public/ 자산 → 그대로
function resolveAssetUrl(url: string): string {
  const v = url.trim();
  if (!v) return "";
  if (v.startsWith("http://") || v.startsWith("https://")) return v;
  if (v.startsWith("/static/")) return `${API_BASE}${v}`;
  return v;
}

export default function SeoSettingsPage() {
  const qc = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["admin", "seo-config"],
    queryFn: fetchSeoConfig,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const [draft, setDraft] = useState<{
    site_name: string;
    site_description: string;
    keywords: string;
    og_image_url: string;
    favicon_url: string;
  } | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  useEffect(() => {
    if (data && draft === null) {
      setDraft({
        site_name: data.site_name,
        site_description: data.site_description,
        keywords: data.keywords,
        og_image_url: data.og_image_url,
        favicon_url: data.favicon_url,
      });
    }
  }, [data, draft]);

  const saveMutation = useMutation({
    mutationFn: (input: NonNullable<typeof draft>) => updateSeoConfig(input),
    onSuccess: (updated: SeoConfig) => {
      qc.setQueryData(["admin", "seo-config"], updated);
      setDraft({
        site_name: updated.site_name,
        site_description: updated.site_description,
        keywords: updated.keywords,
        og_image_url: updated.og_image_url,
        favicon_url: updated.favicon_url,
      });
      setSavedMessage("저장되었습니다. 사이트 화면 새로고침 시 반영됩니다.");
      window.setTimeout(() => setSavedMessage(null), 3500);
    },
  });

  const faviconInputRef = useRef<HTMLInputElement>(null);
  const ogInputRef = useRef<HTMLInputElement>(null);
  const [uploadingKind, setUploadingKind] = useState<"favicon" | "og_image" | null>(
    null,
  );

  const uploadFile = async (kind: "favicon" | "og_image", file: File) => {
    setUploadError(null);
    setUploadingKind(kind);
    try {
      const result = await uploadSeoAsset(kind, file);
      setDraft((prev) =>
        prev === null
          ? prev
          : kind === "favicon"
            ? { ...prev, favicon_url: result.asset_url }
            : { ...prev, og_image_url: result.asset_url },
      );
    } catch (err) {
      setUploadError((err as Error).message);
    } finally {
      setUploadingKind(null);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!draft) return;
    setSavedMessage(null);
    saveMutation.mutate(draft);
  };

  const resetToDefault = () => {
    if (!data) return;
    setDraft({
      site_name: data.default_site_name,
      site_description: data.default_site_description,
      keywords: data.default_keywords,
      og_image_url: data.default_og_image_url,
      favicon_url: data.default_favicon_url,
    });
  };

  const isDirty = useMemo(() => {
    if (!data || !draft) return false;
    return (
      draft.site_name.trim() !== data.site_name ||
      draft.site_description.trim() !== data.site_description ||
      draft.keywords.trim() !== data.keywords ||
      draft.og_image_url.trim() !== data.og_image_url ||
      draft.favicon_url.trim() !== data.favicon_url
    );
  }, [data, draft]);

  const isValid = useMemo(() => {
    if (!draft) return false;
    return (
      draft.site_name.trim().length > 0 &&
      draft.site_description.trim().length > 0 &&
      draft.og_image_url.trim().length > 0 &&
      draft.favicon_url.trim().length > 0
    );
  }, [draft]);

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>SEO 설정</h1>
        <p className={styles.caption}>
          브라우저 탭에 표시되는 사이트 이름, 검색엔진(구글·네이버 등)에 노출되는
          설명·키워드, 카카오톡·페이스북으로 링크를 공유할 때 보이는 미리보기
          이미지(오픈그래프), 즐겨찾기 아이콘(파비콘)을 직접 바꿀 수 있습니다.
          저장하면 즉시 반영되며, 이미 열려 있는 화면은 새로고침해야 보입니다.
        </p>
      </header>

      {isLoading && (
        <p className={styles.statusMessage} role="status">
          현재 설정을 불러오는 중…
        </p>
      )}

      {!isLoading && error && (
        <div className={styles.errorBox} role="alert">
          <p>SEO 설정을 불러오지 못했습니다.</p>
          <button
            type="button"
            className={styles.retryBtn}
            onClick={() => refetch()}
          >
            다시 시도
          </button>
        </div>
      )}

      {draft && data && (
        <form className={styles.card} onSubmit={handleSubmit} noValidate>
          <h2 className={styles.cardTitle}>기본 정보</h2>
          <p className={styles.cardCaption}>
            검색 결과·카카오톡 공유에 함께 표시되는 문구입니다.
          </p>

          <div className={styles.fieldGroup}>
            <label className={styles.fieldLabel} htmlFor="seo-site-name">
              사이트 이름 (브라우저 탭 제목)
            </label>
            <input
              id="seo-site-name"
              type="text"
              className={styles.input}
              value={draft.site_name}
              maxLength={120}
              onChange={(e) =>
                setDraft({ ...draft, site_name: e.target.value })
              }
              placeholder="예) Denvia — 치과 보험청구 AI 어시스턴트"
              required
            />
            <span className={styles.charCount}>
              {draft.site_name.length} / 120
            </span>
          </div>

          <div className={styles.fieldGroup}>
            <label className={styles.fieldLabel} htmlFor="seo-site-description">
              사이트 설명 (검색 결과·공유 미리보기 본문)
            </label>
            <textarea
              id="seo-site-description"
              className={styles.textarea}
              value={draft.site_description}
              maxLength={300}
              onChange={(e) =>
                setDraft({ ...draft, site_description: e.target.value })
              }
              placeholder="검색 결과에 함께 노출됩니다. 80~160자 권장."
              required
            />
            <span className={styles.charCount}>
              {draft.site_description.length} / 300
            </span>
          </div>

          <div className={styles.fieldGroup}>
            <label className={styles.fieldLabel} htmlFor="seo-keywords">
              검색 키워드 (쉼표로 구분)
            </label>
            <input
              id="seo-keywords"
              type="text"
              className={styles.input}
              value={draft.keywords}
              maxLength={300}
              onChange={(e) =>
                setDraft({ ...draft, keywords: e.target.value })
              }
              placeholder="예) 치과, AI 챗봇, 치과 보험청구, 데스크 행정업무"
            />
            <p className={styles.fieldHint}>
              최근 검색엔진은 키워드보다 본문 품질을 우선합니다. 비워두어도
              됩니다.
            </p>
          </div>

          <h2 className={styles.cardTitle}>이미지 자산</h2>
          <p className={styles.cardCaption}>
            업로드 버튼으로 새 이미지를 올리거나, 이미 인터넷에 올라간 이미지
            주소를 붙여넣을 수 있습니다.
          </p>

          {/* 파비콘 */}
          <div className={styles.fieldGroup}>
            <span className={styles.fieldLabel}>
              파비콘 (브라우저 탭 아이콘)
            </span>
            <div className={styles.assetRow}>
              <div className={styles.assetPreviewBox}>
                {draft.favicon_url ? (
                  <img
                    src={resolveAssetUrl(draft.favicon_url)}
                    alt="파비콘 미리보기"
                    className={styles.assetPreviewImg}
                  />
                ) : (
                  <span className={styles.assetPreviewEmpty}>
                    아직 이미지가
                    <br />
                    없습니다
                  </span>
                )}
              </div>
              <div className={styles.assetControls}>
                <input
                  type="text"
                  className={styles.assetUrlInput}
                  value={draft.favicon_url}
                  onChange={(e) =>
                    setDraft({ ...draft, favicon_url: e.target.value })
                  }
                  placeholder="/static/seo-assets/... 또는 https://..."
                />
                <div className={styles.uploadRow}>
                  <button
                    type="button"
                    className={styles.uploadButton}
                    onClick={() => faviconInputRef.current?.click()}
                    disabled={uploadingKind !== null}
                  >
                    {uploadingKind === "favicon"
                      ? "업로드 중…"
                      : "파일 업로드"}
                  </button>
                  <span className={styles.uploadHint}>
                    PNG · ICO · SVG, 5MB 이하. 정사각형 권장.
                  </span>
                  <input
                    ref={faviconInputRef}
                    type="file"
                    accept=".png,.ico,.svg,image/png,image/x-icon,image/vnd.microsoft.icon,image/svg+xml"
                    className={styles.hiddenFileInput}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) void uploadFile("favicon", f);
                      e.target.value = "";
                    }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* OG 이미지 */}
          <div className={styles.fieldGroup}>
            <span className={styles.fieldLabel}>
              오픈그래프 이미지 (카카오톡·페이스북 공유 미리보기)
            </span>
            <div className={styles.assetRow}>
              <div className={`${styles.assetPreviewBox} ${styles.assetPreviewBoxOg}`}>
                {draft.og_image_url ? (
                  <img
                    src={resolveAssetUrl(draft.og_image_url)}
                    alt="OG 이미지 미리보기"
                    className={styles.assetPreviewImg}
                  />
                ) : (
                  <span className={styles.assetPreviewEmpty}>
                    아직 이미지가
                    <br />
                    없습니다
                  </span>
                )}
              </div>
              <div className={styles.assetControls}>
                <input
                  type="text"
                  className={styles.assetUrlInput}
                  value={draft.og_image_url}
                  onChange={(e) =>
                    setDraft({ ...draft, og_image_url: e.target.value })
                  }
                  placeholder="/static/seo-assets/... 또는 https://..."
                />
                <div className={styles.uploadRow}>
                  <button
                    type="button"
                    className={styles.uploadButton}
                    onClick={() => ogInputRef.current?.click()}
                    disabled={uploadingKind !== null}
                  >
                    {uploadingKind === "og_image"
                      ? "업로드 중…"
                      : "파일 업로드"}
                  </button>
                  <span className={styles.uploadHint}>
                    PNG · JPG · WEBP, 5MB 이하. 1200×630 권장.
                  </span>
                  <input
                    ref={ogInputRef}
                    type="file"
                    accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
                    className={styles.hiddenFileInput}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) void uploadFile("og_image", f);
                      e.target.value = "";
                    }}
                  />
                </div>
              </div>
            </div>
          </div>

          {uploadError && (
            <p className={styles.errorText} role="alert">
              {uploadError}
            </p>
          )}

          <div className={styles.actionsRow}>
            <button
              type="submit"
              className={styles.saveBtn}
              disabled={saveMutation.isPending || !isDirty || !isValid}
            >
              {saveMutation.isPending ? "저장 중…" : "저장"}
            </button>
            <button
              type="button"
              className={styles.resetBtn}
              onClick={resetToDefault}
              disabled={saveMutation.isPending}
            >
              기본값으로 되돌리기
            </button>
            {savedMessage && (
              <span className={styles.successText} role="status">
                {savedMessage}
              </span>
            )}
            {saveMutation.isError && (
              <span className={styles.errorText} role="alert">
                {(saveMutation.error as Error)?.message ?? "저장에 실패했습니다."}
              </span>
            )}
          </div>

          <div className={styles.previewCard}>
            <span className={styles.previewLabel}>검색 결과 미리보기</span>
            <div className={styles.searchPreview}>
              <span className={styles.searchPreviewUrl}>denvia.kr</span>
              <span className={styles.searchPreviewTitle}>
                {draft.site_name || "사이트 이름"}
              </span>
              <span className={styles.searchPreviewDesc}>
                {draft.site_description || "사이트 설명"}
              </span>
            </div>

            <span className={styles.previewLabel}>
              카카오톡 / 페이스북 공유 미리보기
            </span>
            <div className={styles.ogPreview}>
              <div className={styles.ogPreviewImageBox}>
                {draft.og_image_url ? (
                  <img
                    src={resolveAssetUrl(draft.og_image_url)}
                    alt="공유 미리보기"
                    className={styles.ogPreviewImage}
                  />
                ) : (
                  <span className={styles.ogPreviewImageEmpty}>
                    이미지 없음
                  </span>
                )}
              </div>
              <div className={styles.ogPreviewBody}>
                <span className={styles.ogPreviewDomain}>DENVIA.KR</span>
                <span className={styles.ogPreviewTitle}>
                  {draft.site_name || "사이트 이름"}
                </span>
                <span className={styles.ogPreviewDesc}>
                  {draft.site_description || "사이트 설명"}
                </span>
              </div>
            </div>
          </div>
        </form>
      )}
    </section>
  );
}
