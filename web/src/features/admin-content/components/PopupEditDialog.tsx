"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  ApiError,
  PopupDetail,
  PopupFormInput,
  createPopup,
  fetchPopupDetail,
  popupFormSchema,
  updatePopup,
  uploadPopupImage,
} from "@/features/admin-content/api/popup";
import { PopupPreviewCard } from "./PopupPreviewCard";
import styles from "./PopupEditDialog.module.css";

const RichTextEditor = dynamic(
  () =>
    import("@/components/editor/RichTextEditor").then((m) => m.RichTextEditor),
  {
    ssr: false,
    loading: () => (
      <p role="status" className={styles.editorLoading}>
        에디터를 불러오는 중…
      </p>
    ),
  },
);

interface Props {
  mode: "create" | "edit";
  popupId?: number;
  onClose: () => void;
  onSaved: () => void;
}

type FieldErrors = Partial<Record<keyof PopupFormInput, string>>;

const EMPTY_FORM: PopupFormInput = {
  title: "",
  popup_type: "editor",
  target_device: "both",
  body_html: "",
  image_url: "",
  link_url: "",
  display_start: "",
  display_end: "",
  target_segment: "all",
  sort_order: 0,
  is_active: true,
};

function toLocalInput(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}`;
}

export function PopupEditDialog({ mode, popupId, onClose, onSaved }: Props) {
  const [form, setForm] = useState<PopupFormInput>(EMPTY_FORM);
  const [loading, setLoading] = useState(mode === "edit");
  const [submitting, setSubmitting] = useState(false);
  const [uploadingImage, setUploadingImage] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [globalError, setGlobalError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !submitting) onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose, submitting]);

  useEffect(() => {
    if (mode !== "edit" || !popupId) return;
    let cancelled = false;
    fetchPopupDetail(popupId)
      .then((detail: PopupDetail) => {
        if (cancelled) return;
        setForm({
          title: detail.title,
          popup_type: detail.popup_type,
          target_device: detail.target_device,
          body_html: detail.body_html ?? "",
          image_url: detail.image_url ?? "",
          link_url: detail.link_url ?? "",
          display_start: toLocalInput(detail.display_start),
          display_end: toLocalInput(detail.display_end),
          target_segment: detail.target_segment,
          sort_order: detail.sort_order,
          is_active: detail.is_active,
        });
      })
      .catch(() => setGlobalError("팝업 정보를 불러오지 못했습니다."))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [mode, popupId]);

  function update<K extends keyof PopupFormInput>(
    key: K,
    value: PopupFormInput[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => ({ ...prev, [key]: undefined }));
  }

  async function handleImageFile(file: File) {
    setUploadingImage(true);
    setErrors((prev) => ({ ...prev, image_url: undefined }));
    try {
      const res = await uploadPopupImage(file);
      update("image_url", res.image_url);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors((prev) => ({ ...prev, image_url: err.message }));
      } else {
        setErrors((prev) => ({
          ...prev,
          image_url: "이미지 업로드에 실패했습니다.",
        }));
      }
    } finally {
      setUploadingImage(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setGlobalError(null);

    const parsed = popupFormSchema.safeParse(form);
    if (!parsed.success) {
      const fieldErrors: FieldErrors = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0] as keyof PopupFormInput | undefined;
        if (key && !fieldErrors[key]) fieldErrors[key] = issue.message;
      }
      setErrors(fieldErrors);
      return;
    }

    setSubmitting(true);
    try {
      if (mode === "create") {
        await createPopup(parsed.data);
      } else if (popupId) {
        await updatePopup(popupId, parsed.data);
      }
      onSaved();
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === "POPUP_DISPLAY_RANGE_INVALID") {
          setErrors({ display_end: err.message });
        } else if (err.code === "POPUP_LINK_URL_INVALID") {
          setErrors({ link_url: err.message });
        } else if (
          err.code === "POPUP_IMAGE_REQUIRED" ||
          err.code === "POPUP_IMAGE_URL_INVALID"
        ) {
          setErrors({ image_url: err.message });
        } else if (err.code === "POPUP_BODY_REQUIRED") {
          setErrors({ body_html: err.message });
        } else {
          setGlobalError(err.message);
        }
      } else {
        setGlobalError("저장에 실패했습니다. 잠시 후 다시 시도해주세요.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="presentation"
      className={styles.overlay}
      onClick={(e) => {
        if (e.target === e.currentTarget && !submitting) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="popup-edit-title"
        className={styles.dialog}
      >
        <header className={styles.header}>
          <h2 id="popup-edit-title" className={styles.heading}>
            {mode === "create" ? "팝업 작성" : "팝업 편집"}
          </h2>
          <button
            type="button"
            aria-label="닫기"
            className={styles.closeBtn}
            disabled={submitting}
            onClick={onClose}
          >
            ✕
          </button>
        </header>

        {loading ? (
          <p className={styles.loading} role="status">
            불러오는 중…
          </p>
        ) : (
          <form className={styles.form} onSubmit={handleSubmit} noValidate>
            <div className={styles.grid}>
              <section className={styles.fields}>
                <label className={styles.field}>
                  <span className={styles.label}>제목</span>
                  <input
                    type="text"
                    value={form.title}
                    maxLength={200}
                    onChange={(e) => update("title", e.target.value)}
                    aria-invalid={Boolean(errors.title)}
                  />
                  <span className={styles.helper}>최대 200자</span>
                  {errors.title ? (
                    <p role="alert" className={styles.error}>
                      {errors.title}
                    </p>
                  ) : null}
                </label>

                <fieldset className={styles.field}>
                  <legend className={styles.label}>노출 디바이스</legend>
                  {(
                    [
                      ["both", "PC + 모바일"],
                      ["pc", "PC만"],
                      ["mobile", "모바일만"],
                    ] as const
                  ).map(([value, label]) => (
                    <label key={value} className={styles.radioLabel}>
                      <input
                        type="radio"
                        name="target_device"
                        value={value}
                        checked={form.target_device === value}
                        onChange={() => update("target_device", value)}
                      />
                      {label}
                    </label>
                  ))}
                </fieldset>

                <fieldset className={styles.field}>
                  <legend className={styles.label}>팝업 타입</legend>
                  {(
                    [
                      ["editor", "에디터(텍스트+이미지)"],
                      ["image", "이미지만"],
                    ] as const
                  ).map(([value, label]) => (
                    <label key={value} className={styles.radioLabel}>
                      <input
                        type="radio"
                        name="popup_type"
                        value={value}
                        checked={form.popup_type === value}
                        onChange={() => update("popup_type", value)}
                      />
                      {label}
                    </label>
                  ))}
                </fieldset>

                {form.popup_type === "image" ? (
                  <div className={styles.field}>
                    <span className={styles.label}>이미지</span>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) void handleImageFile(file);
                      }}
                      disabled={uploadingImage || submitting}
                    />
                    {uploadingImage ? (
                      <p role="status" className={styles.helper}>
                        업로드 중…
                      </p>
                    ) : null}
                    {form.image_url ? (
                      <div className={styles.imagePreview}>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={form.image_url} alt="업로드 이미지 미리보기" />
                        <button
                          type="button"
                          className={styles.imageRemoveBtn}
                          onClick={() => {
                            update("image_url", "");
                            if (fileInputRef.current) {
                              fileInputRef.current.value = "";
                            }
                          }}
                        >
                          이미지 제거
                        </button>
                      </div>
                    ) : null}
                    <span className={styles.helper}>
                      PNG·JPG·WEBP, 5MB 이하
                    </span>
                    {errors.image_url ? (
                      <p role="alert" className={styles.error}>
                        {errors.image_url}
                      </p>
                    ) : null}
                  </div>
                ) : (
                  <div className={styles.field}>
                    <span className={styles.label}>본문</span>
                    <RichTextEditor
                      value={form.body_html ?? ""}
                      onChange={(html) => update("body_html", html)}
                      ariaLabel="팝업 본문"
                    />
                    {errors.body_html ? (
                      <p role="alert" className={styles.error}>
                        {errors.body_html}
                      </p>
                    ) : null}
                  </div>
                )}

                <label className={styles.field}>
                  <span className={styles.label}>노출 시작</span>
                  <input
                    type="datetime-local"
                    value={form.display_start}
                    onChange={(e) => update("display_start", e.target.value)}
                  />
                  {errors.display_start ? (
                    <p role="alert" className={styles.error}>
                      {errors.display_start}
                    </p>
                  ) : null}
                </label>

                <label className={styles.field}>
                  <span className={styles.label}>노출 종료</span>
                  <input
                    type="datetime-local"
                    value={form.display_end}
                    onChange={(e) => update("display_end", e.target.value)}
                    aria-invalid={Boolean(errors.display_end)}
                  />
                  {errors.display_end ? (
                    <p role="alert" className={styles.error}>
                      {errors.display_end}
                    </p>
                  ) : null}
                </label>

                <fieldset className={styles.field}>
                  <legend className={styles.label}>타겟 가입유형</legend>
                  {(
                    [
                      ["all", "전체"],
                      ["doctor", "의사"],
                      ["hygienist", "위생사"],
                      ["student_other", "학생·기타"],
                    ] as const
                  ).map(([value, label]) => (
                    <label key={value} className={styles.radioLabel}>
                      <input
                        type="radio"
                        name="target_segment"
                        value={value}
                        checked={form.target_segment === value}
                        onChange={() => update("target_segment", value)}
                      />
                      {label}
                    </label>
                  ))}
                </fieldset>

                <label className={styles.field}>
                  <span className={styles.label}>노출 순서</span>
                  <input
                    type="number"
                    min={0}
                    max={999}
                    value={form.sort_order}
                    onChange={(e) =>
                      update("sort_order", Number(e.target.value) || 0)
                    }
                  />
                  <span className={styles.helper}>
                    작은 값이 먼저 노출됩니다 (0~999)
                  </span>
                  {errors.sort_order ? (
                    <p role="alert" className={styles.error}>
                      {errors.sort_order}
                    </p>
                  ) : null}
                </label>

                <label className={styles.field}>
                  <span className={styles.label}>링크 URL (선택)</span>
                  <input
                    type="url"
                    value={form.link_url ?? ""}
                    placeholder="https://example.com"
                    maxLength={500}
                    onChange={(e) => update("link_url", e.target.value)}
                    aria-invalid={Boolean(errors.link_url)}
                  />
                  <span className={styles.helper}>
                    외부 링크는 새 탭으로 열리며 http(s)://만 허용됩니다.
                  </span>
                  {errors.link_url ? (
                    <p role="alert" className={styles.error}>
                      {errors.link_url}
                    </p>
                  ) : null}
                </label>

                {mode === "edit" ? (
                  <label className={styles.fieldRow}>
                    <input
                      type="checkbox"
                      checked={form.is_active}
                      onChange={(e) => update("is_active", e.target.checked)}
                    />
                    <span>활성 노출</span>
                  </label>
                ) : null}
              </section>

              <aside className={styles.preview}>
                <h3 className={styles.previewHeading}>미리보기</h3>
                <PopupPreviewCard
                  title={form.title}
                  bodyHtml={
                    form.popup_type === "image" && form.image_url
                      ? `<img src="${form.image_url}" alt="${form.title}" />`
                      : form.body_html ?? ""
                  }
                  linkUrl={form.link_url || null}
                />
              </aside>
            </div>

            {globalError ? (
              <p role="alert" className={styles.globalError}>
                {globalError}
              </p>
            ) : null}

            <footer className={styles.footer}>
              <button
                type="button"
                className={styles.cancelBtn}
                onClick={onClose}
                disabled={submitting}
              >
                취소
              </button>
              <button
                type="submit"
                className={styles.submitBtn}
                disabled={submitting || uploadingImage}
              >
                {submitting ? "저장 중…" : "저장"}
              </button>
            </footer>
          </form>
        )}
      </div>
    </div>
  );
}
