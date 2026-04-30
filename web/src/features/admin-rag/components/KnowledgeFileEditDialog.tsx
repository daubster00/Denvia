"use client";

import { useEffect, useRef, useState } from "react";
import { IconClose } from "@wanteddev/wds-icon";
import { fetchKnowledgeDetail, editKnowledge } from "../api/knowledge";
import styles from "./KnowledgeFileEditDialog.module.css";

function escapeHtml(s: string) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function highlightLine(line: string): string {
  const e = escapeHtml(line);
  if (line.startsWith("{") && line.endsWith("}") && line.length > 2)
    return `<span class="${styles.major}">${e}</span>`;
  if (line.startsWith("=") && line.endsWith("=") && line.length >= 2)
    return `<span class="${styles.minor}">${e}</span>`;
  return e;
}

export function toHighlightHtml(text: string): string {
  return text.split("\n").map(highlightLine).join("\n") + "\n";
}

interface Props {
  uploadId: number;
  onClose: () => void;
  onSaved: () => void;
}

export function KnowledgeFileEditDialog({ uploadId, onClose, onSaved }: Props) {
  const [content, setContent] = useState("");
  const [filename, setFilename] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const preRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetchKnowledgeDetail(uploadId)
      .then((d) => {
        if (!cancelled) {
          setContent(d.content);
          setFilename(d.filename);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError((e as Error).message);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [uploadId]);

  useEffect(() => {
    const handle = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handle);
    return () => document.removeEventListener("keydown", handle);
  }, [onClose]);

  const syncScroll = () => {
    if (preRef.current && textareaRef.current) {
      preRef.current.scrollTop = textareaRef.current.scrollTop;
      preRef.current.scrollLeft = textareaRef.current.scrollLeft;
    }
  };

  const handleSave = async () => {
    setError(null);
    setSaving(true);
    try {
      await editKnowledge(uploadId, content);
      onSaved();
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      role="presentation"
      className={styles.overlay}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`편집: ${filename}`}
        className={styles.dialog}
      >
        <div className={styles.header}>
          <h2 className={styles.title}>{filename} 편집</h2>
          <button
            type="button"
            onClick={onClose}
            className={styles.closeBtn}
            aria-label="닫기"
          >
            <IconClose aria-hidden />
          </button>
        </div>

        {loading && <div className={styles.loadingText}>불러오는 중…</div>}
        {!loading && (
          <div className={styles.editorWrapper}>
            <pre
              ref={preRef}
              aria-hidden="true"
              className={styles.highlight}
              dangerouslySetInnerHTML={{ __html: toHighlightHtml(content) }}
            />
            <textarea
              ref={textareaRef}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              onScroll={syncScroll}
              className={styles.textarea}
              spellCheck={false}
              autoComplete="off"
            />
          </div>
        )}

        {error && <p className={styles.errorMsg}>{error}</p>}

        <div className={styles.actions}>
          <button
            type="button"
            onClick={onClose}
            className={styles.cancelBtn}
          >
            취소
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || loading}
            className={styles.saveBtn}
          >
            {saving ? "저장 중…" : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}
