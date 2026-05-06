"use client";

import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import Image from "@tiptap/extension-image";
import { useCallback, useEffect } from "react";
import styles from "./RichTextEditor.module.css";

interface Props {
  value: string;
  onChange: (html: string) => void;
  placeholder?: string;
  ariaLabel?: string;
}

const HTTP_RX = /^https?:\/\//i;

export function RichTextEditor({ value, onChange, ariaLabel }: Props) {
  const editor = useEditor({
    extensions: [
      StarterKit,
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
    content: value,
    immediatelyRender: false,
    onUpdate: ({ editor: ed }) => {
      onChange(ed.getHTML());
    },
  });

  // 외부에서 value가 바뀐 경우(편집 다이얼로그 prefill) 동기화
  useEffect(() => {
    if (!editor) return;
    if (editor.getHTML() !== value) {
      editor.commands.setContent(value, { emitUpdate: false });
    }
    // editor를 deps에 넣으면 매 입력마다 setContent가 다시 발생 → 무한 루프
    // value만 deps로 두고 비교는 위 if문이 담당.
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

  const handleAddImage = useCallback(() => {
    if (!editor) return;
    const url = window.prompt("이미지 URL (https:// 또는 http://)");
    if (!url) return;
    if (!HTTP_RX.test(url)) {
      window.alert("http:// 또는 https://로 시작하는 URL을 입력해주세요.");
      return;
    }
    editor.chain().focus().setImage({ src: url }).run();
  }, [editor]);

  if (!editor) return null;

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
        <button
          type="button"
          aria-label="링크 삽입"
          onClick={handleAddLink}
          className={styles.btn}
        >
          링크
        </button>
        <button
          type="button"
          aria-label="이미지 삽입"
          onClick={handleAddImage}
          className={styles.btn}
        >
          이미지
        </button>
      </div>
      <EditorContent editor={editor} className={styles.editorContent} />
    </div>
  );
}
