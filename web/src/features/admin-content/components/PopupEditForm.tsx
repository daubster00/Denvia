"use client";

import { useEffect, useId, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  Button,
  Checkbox,
  Label,
  RadioGroup,
  RadioGroupItem,
  TextButton,
} from "@wanteddev/wds";
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
import { resolveAssetUrl } from "@/lib/asset-url";
import { PopupPositionPreview } from "./PopupPositionPreview";
import styles from "./PopupEditForm.module.css";

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
  onCancel: () => void;
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
  display_position: "center",
  sort_order: 0,
  is_active: true,
};

const POSITION_OPTIONS = [
  ["center", "가운데"],
  ["top", "위"],
  ["bottom", "아래"],
  ["bottom_left", "좌하단"],
  ["bottom_right", "우하단"],
] as const;

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

export function PopupEditForm({ mode, popupId, onCancel, onSaved }: Props) {
  const [form, setForm] = useState<PopupFormInput>(EMPTY_FORM);
  const [loading, setLoading] = useState(mode === "edit");
  const [submitting, setSubmitting] = useState(false);
  const [uploadingImage, setUploadingImage] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const idPrefix = useId();
  const fileInputId = `${idPrefix}-popup-image`;

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
          display_position: detail.display_position ?? "center",
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

  useEffect(() => {
    if (!previewOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPreviewOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [previewOpen]);

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

  if (loading) {
    return (
      <p className={styles.loading} role="status">
        불러오는 중…
      </p>
    );
  }

  return (
    <>
      <form className={styles.form} onSubmit={handleSubmit} noValidate>
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

          <div className={styles.field}>
            <span className={styles.label}>노출 디바이스</span>
            <RadioGroup
              name="target_device"
              value={form.target_device}
              onValueChange={(v) =>
                update("target_device", v as PopupFormInput["target_device"])
              }
              orientation="horizontal"
            >
              <div className={styles.radioRow}>
                {(
                  [
                    ["both", "PC + 모바일"],
                    ["pc", "PC만"],
                    ["mobile", "모바일만"],
                  ] as const
                ).map(([value, label]) => {
                  const id = `${idPrefix}-device-${value}`;
                  return (
                    <div key={value} className={styles.radioItem}>
                      <RadioGroupItem id={id} value={value} size="small" />
                      <Label htmlFor={id}>{label}</Label>
                    </div>
                  );
                })}
              </div>
            </RadioGroup>
          </div>

          <div className={styles.field}>
            <span className={styles.label}>팝업 타입</span>
            <RadioGroup
              name="popup_type"
              value={form.popup_type}
              onValueChange={(v) =>
                update("popup_type", v as PopupFormInput["popup_type"])
              }
              orientation="horizontal"
            >
              <div className={styles.radioRow}>
                {(
                  [
                    ["editor", "에디터(텍스트+이미지)"],
                    ["image", "이미지만"],
                  ] as const
                ).map(([value, label]) => {
                  const id = `${idPrefix}-type-${value}`;
                  return (
                    <div key={value} className={styles.radioItem}>
                      <RadioGroupItem id={id} value={value} size="small" />
                      <Label htmlFor={id}>{label}</Label>
                    </div>
                  );
                })}
              </div>
            </RadioGroup>
          </div>

          {form.popup_type === "image" ? (
            <div className={styles.field}>
              <span className={styles.label}>이미지</span>
              <div className={styles.fileRow}>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void handleImageFile(file);
                  }}
                  disabled={uploadingImage || submitting}
                  id={fileInputId}
                  className={styles.fileInputHidden}
                />
                <Button
                  as="label"
                  htmlFor={fileInputId}
                  variant="outlined"
                  color="assistive"
                  size="small"
                  disabled={uploadingImage || submitting}
                  loading={uploadingImage}
                >
                  {uploadingImage ? "업로드 중…" : "이미지 선택"}
                </Button>
                <span className={styles.fileHint}>PNG·JPG·WEBP, 5MB 이하</span>
              </div>
              {form.image_url ? (
                <div className={styles.imagePreview}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={resolveAssetUrl(form.image_url)}
                    alt="업로드 이미지 미리보기"
                  />
                  <TextButton
                    color="assistive"
                    size="small"
                    onClick={() => {
                      update("image_url", "");
                      if (fileInputRef.current) {
                        fileInputRef.current.value = "";
                      }
                    }}
                  >
                    이미지 제거
                  </TextButton>
                </div>
              ) : null}
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
                onImageUpload={async (file) => {
                  const res = await uploadPopupImage(file);
                  return res.image_url;
                }}
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

          <div className={styles.field}>
            <span className={styles.label}>타겟 가입유형</span>
            <RadioGroup
              name="target_segment"
              value={form.target_segment}
              onValueChange={(v) =>
                update("target_segment", v as PopupFormInput["target_segment"])
              }
              orientation="horizontal"
            >
              <div className={styles.radioRow}>
                {(
                  [
                    ["all", "전체"],
                    ["doctor", "의사"],
                    ["hygienist", "위생사"],
                    ["student_other", "학생·기타"],
                  ] as const
                ).map(([value, label]) => {
                  const id = `${idPrefix}-seg-${value}`;
                  return (
                    <div key={value} className={styles.radioItem}>
                      <RadioGroupItem id={id} value={value} size="small" />
                      <Label htmlFor={id}>{label}</Label>
                    </div>
                  );
                })}
              </div>
            </RadioGroup>
          </div>

          <div
            className={styles.field}
            data-disabled={
              form.target_device === "mobile" ? "true" : undefined
            }
          >
            <span className={styles.label}>노출 위치 (PC)</span>
            <RadioGroup
              name="display_position"
              value={form.display_position}
              onValueChange={(v) =>
                update(
                  "display_position",
                  v as PopupFormInput["display_position"],
                )
              }
              orientation="horizontal"
              disabled={form.target_device === "mobile"}
            >
              <div className={styles.radioRow}>
                {POSITION_OPTIONS.map(([value, label]) => {
                  const id = `${idPrefix}-pos-${value}`;
                  return (
                    <div key={value} className={styles.radioItem}>
                      <RadioGroupItem id={id} value={value} size="small" />
                      <Label htmlFor={id}>{label}</Label>
                    </div>
                  );
                })}
              </div>
            </RadioGroup>
            <span className={styles.helper}>
              모바일에서는 화면이 좁아 항상 가운데 고정이며, 여러 개일 때는
              슬라이드로 넘어갑니다.
            </span>
          </div>

          <label className={styles.field}>
            <span className={styles.label}>노출 순서</span>
            <input
              type="number"
              min={0}
              max={999}
              value={form.sort_order === 0 ? "" : form.sort_order}
              placeholder="0"
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
            <div className={styles.fieldRow}>
              <Checkbox
                id={`${idPrefix}-active`}
                checked={form.is_active}
                onCheckedChange={(state) => update("is_active", state)}
                size="small"
              />
              <Label htmlFor={`${idPrefix}-active`}>활성 노출</Label>
            </div>
          ) : null}
        </section>

        {globalError ? (
          <p role="alert" className={styles.globalError}>
            {globalError}
          </p>
        ) : null}

        <footer className={styles.footer}>
          <div className={styles.footerLeft}>
            <Button
              type="button"
              variant="outlined"
              color="assistive"
              size="medium"
              onClick={() => setPreviewOpen(true)}
            >
              미리보기
            </Button>
          </div>
          <div className={styles.footerRight}>
            <Button
              type="button"
              variant="outlined"
              color="assistive"
              size="medium"
              onClick={onCancel}
              disabled={submitting}
            >
              취소
            </Button>
            <Button
              type="submit"
              variant="solid"
              color="primary"
              size="medium"
              loading={submitting}
              disabled={submitting || uploadingImage}
            >
              {submitting ? "저장 중…" : "저장"}
            </Button>
          </div>
        </footer>
      </form>

      {previewOpen ? (
        <div
          role="presentation"
          className={styles.previewOverlay}
          onClick={(e) => {
            if (e.target === e.currentTarget) setPreviewOpen(false);
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="popup-preview-title"
            className={styles.previewModal}
          >
            <header className={styles.previewModalHeader}>
              <h3
                id="popup-preview-title"
                className={styles.previewModalHeading}
              >
                미리보기
              </h3>
              <TextButton
                aria-label="미리보기 닫기"
                color="assistive"
                size="small"
                onClick={() => setPreviewOpen(false)}
              >
                닫기
              </TextButton>
            </header>
            <div className={styles.previewModalBody}>
              <PopupPositionPreview form={form} />
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
