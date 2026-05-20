"use client";

import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import Image from "@tiptap/extension-image";
import { TextStyle, Color, FontSize } from "@tiptap/extension-text-style";
import { useCallback, useEffect, useRef, useState } from "react";
import { resolveAssetUrl, toEditorHtml } from "@/lib/asset-url";
import styles from "./RichTextEditor.module.css";

interface Props {
  value: string;
  onChange: (html: string) => void;
  placeholder?: string;
  ariaLabel?: string;
  onImageUpload?: (file: File) => Promise<string>;
}

const HTTP_RX = /^https?:\/\//i;
const ACCEPT = "image/png,image/jpeg,image/webp";

// 팝업 본문 sanitizer가 허용하는 8가지 프리셋 색 — 서버/클라이언트 sanitizer와 동기.
const PRESET_COLORS: Array<{ name: string; hex: string }> = [
  { name: "검정", hex: "#18181b" },
  { name: "회색", hex: "#6b7280" },
  { name: "빨강", hex: "#dc2626" },
  { name: "주황", hex: "#ea580c" },
  { name: "노랑", hex: "#ca8a04" },
  { name: "초록", hex: "#16a34a" },
  { name: "파랑", hex: "#2563eb" },
  { name: "보라", hex: "#7c3aed" },
];

const FONT_SIZES_PX = [12, 14, 16, 20, 24] as const;
const DEFAULT_FONT_SIZE_PX = 16;

export function RichTextEditor({
  value,
  onChange,
  ariaLabel,
  onImageUpload,
}: Props) {
  const editor = useEditor({
    extensions: [
      StarterKit,
      TextStyle,
      Color,
      FontSize,
      Link.configure({
        openOnClick: false,
        autolink: false,
        HTMLAttributes: { rel: "noopener noreferrer", target: "_blank" },
        validate: (href) => HTTP_RX.test(href),
      }),
      Image.configure({
        HTMLAttributes: { class: styles.embeddedImage },
      }),
    ],
    // 백엔드 상대경로 `/static/...` 를 API 서버 absolute URL 로 변환해 에디터 안에서
    // 이미지가 정상 렌더되도록 한다. value 가 비어있으면 그대로 통과.
    content: toEditorHtml(value),
    immediatelyRender: false,
    onUpdate: ({ editor: ed }) => {
      onChange(ed.getHTML());
    },
  });

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isColorPickerOpen, setIsColorPickerOpen] = useState(false);
  const colorPickerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isColorPickerOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (
        colorPickerRef.current &&
        !colorPickerRef.current.contains(e.target as Node)
      ) {
        setIsColorPickerOpen(false);
      }
    };
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsColorPickerOpen(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [isColorPickerOpen]);

  useEffect(() => {
    if (!editor) return;
    // 에디터 안에서는 항상 absolute URL 형태로 비교/세팅한다.
    // (DB 가 상대경로로 저장돼 있어도 동일하게 absolute 로 정규화해 비교)
    const desired = toEditorHtml(value);
    if (editor.getHTML() !== desired) {
      editor.commands.setContent(desired, { emitUpdate: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const handleAddLink = useCallback(() => {
    if (!editor) return;
    const url = window.prompt("링크 URL (https:// 또는 http://)");
    if (!url) return;
    if (!HTTP_RX.test(url)) {
      window.alert("http:// 또는 https://로 시작하는 URL을 입력해주세요.");
      return;
    }
    editor.chain().focus().setLink({ href: url }).run();
  }, [editor]);

  const handleImageButtonClick = useCallback(() => {
    if (!onImageUpload) return;
    setUploadError(null);
    fileInputRef.current?.click();
  }, [onImageUpload]);

  const handleFileChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (!file || !editor || !onImageUpload) return;
      setUploading(true);
      setUploadError(null);
      try {
        const url = await onImageUpload(file);
        // 백엔드가 `/static/...` 상대경로를 돌려주면 그대로 src 에 박을 경우
        // 웹앱 origin 기준으로 해석돼 broken image 가 된다. API 서버 absolute URL 로 변환.
        editor.chain().focus().setImage({ src: resolveAssetUrl(url) }).run();
      } catch (err) {
        setUploadError(
          err instanceof Error ? err.message : "이미지 업로드에 실패했습니다.",
        );
      } finally {
        setUploading(false);
      }
    },
    [editor, onImageUpload],
  );

  const handleColorClick = useCallback(
    (hex: string) => {
      if (!editor) return;
      // 기본색(검정)을 다시 누르면 마크 해제 → 깔끔한 HTML.
      if (hex === PRESET_COLORS[0].hex) {
        editor.chain().focus().unsetColor().run();
      } else {
        editor.chain().focus().setColor(hex).run();
      }
      setIsColorPickerOpen(false);
    },
    [editor],
  );

  const handleFontSizeChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      if (!editor) return;
      const px = parseInt(e.target.value, 10);
      const chain = editor.chain().focus() as unknown as {
        setFontSize: (size: string) => { run: () => boolean };
        unsetFontSize: () => { run: () => boolean };
      };
      if (px === DEFAULT_FONT_SIZE_PX) {
        chain.unsetFontSize().run();
      } else {
        chain.setFontSize(`${px}px`).run();
      }
    },
    [editor],
  );

  if (!editor) return null;

  const currentFontSize: string | null =
    (editor.getAttributes("textStyle") as { fontSize?: string | null })
      .fontSize ?? null;
  const currentColor: string | null =
    (editor.getAttributes("textStyle") as { color?: string | null }).color ??
    null;

  return (
    <div className={styles.wrapper} aria-label={ariaLabel}>
      <div className={styles.toolbar} role="toolbar" aria-label="서식 도구">
        <button
          type="button"
          aria-label="굵게"
          aria-pressed={editor.isActive("bold")}
          onClick={() => editor.chain().focus().toggleBold().run()}
          className={editor.isActive("bold") ? styles.btnActive : styles.btn}
        >
          B
        </button>
        <button
          type="button"
          aria-label="기울임"
          aria-pressed={editor.isActive("italic")}
          onClick={() => editor.chain().focus().toggleItalic().run()}
          className={editor.isActive("italic") ? styles.btnActive : styles.btn}
        >
          I
        </button>
        <button
          type="button"
          aria-label="밑줄"
          aria-pressed={editor.isActive("underline")}
          onClick={() => editor.chain().focus().toggleUnderline().run()}
          className={editor.isActive("underline") ? styles.btnActive : styles.btn}
        >
          U
        </button>
        <button
          type="button"
          aria-label="글머리 기호 목록"
          aria-pressed={editor.isActive("bulletList")}
          onClick={() => editor.chain().focus().toggleBulletList().run()}
          className={
            editor.isActive("bulletList") ? styles.btnActive : styles.btn
          }
        >
          •
        </button>
        <button
          type="button"
          aria-label="번호 매기기 목록"
          aria-pressed={editor.isActive("orderedList")}
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
          className={
            editor.isActive("orderedList") ? styles.btnActive : styles.btn
          }
        >
          1.
        </button>
        <span className={styles.toolbarDivider} aria-hidden="true" />
        <label className={styles.fontSizeLabel}>
          <span className={styles.srOnly}>글자 크기</span>
          <select
            aria-label="글자 크기"
            className={styles.fontSizeSelect}
            value={
              currentFontSize
                ? currentFontSize.replace("px", "")
                : String(DEFAULT_FONT_SIZE_PX)
            }
            onChange={handleFontSizeChange}
          >
            {FONT_SIZES_PX.map((px) => (
              <option key={px} value={px}>
                {px}px
              </option>
            ))}
          </select>
        </label>
        <div className={styles.colorPicker} ref={colorPickerRef}>
          <button
            type="button"
            aria-label="글자 색"
            aria-haspopup="true"
            aria-expanded={isColorPickerOpen}
            className={styles.colorPickerButton}
            onClick={() => setIsColorPickerOpen((v) => !v)}
          >
            <span className={styles.colorPickerIcon} aria-hidden="true">
              A
            </span>
            <span
              className={styles.colorPickerUnderline}
              data-color={currentColor ?? PRESET_COLORS[0].hex}
              aria-hidden="true"
            />
          </button>
          {isColorPickerOpen ? (
            <div
              className={styles.colorPopover}
              role="group"
              aria-label="글자 색 선택"
            >
              {PRESET_COLORS.map((c) => {
                const isActive =
                  c.hex === PRESET_COLORS[0].hex
                    ? !currentColor
                    : currentColor?.toLowerCase() === c.hex;
                return (
                  <button
                    key={c.hex}
                    type="button"
                    aria-label={`글자색 ${c.name}`}
                    aria-pressed={isActive}
                    title={c.name}
                    className={`${styles.colorSwatch} ${
                      isActive ? styles.colorSwatchActive : ""
                    }`}
                    data-color={c.hex}
                    data-no-admin-height
                    onClick={() => handleColorClick(c.hex)}
                  />
                );
              })}
            </div>
          ) : null}
        </div>
        <span className={styles.toolbarDivider} aria-hidden="true" />
        <button
          type="button"
          aria-label="링크 삽입"
          onClick={handleAddLink}
          className={styles.btn}
        >
          링크
        </button>
        {onImageUpload ? (
          <>
            <button
              type="button"
              aria-label="이미지 삽입"
              onClick={handleImageButtonClick}
              disabled={uploading}
              className={styles.btn}
            >
              {uploading ? "업로드 중…" : "이미지"}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT}
              className={styles.hiddenFileInput}
              onChange={handleFileChange}
            />
          </>
        ) : null}
      </div>
      {uploadError ? (
        <p role="alert" className={styles.uploadError}>
          {uploadError}
        </p>
      ) : null}
      <EditorContent editor={editor} className={styles.editorContent} />
    </div>
  );
}
