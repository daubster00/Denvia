"use client";

import { useEffect, useRef, useState } from "react";
import { IconClose } from "@wanteddev/wds-icon";
import { fetchKnowledgeDetail, editKnowledge } from "../api/knowledge";
import styles from "./KnowledgeFileEditDialog.module.css";

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
  const mouseDownOnOverlayRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    fetchKnowledgeDetail(uploadId)
      .then((d) => {
        if (!cancelled) {
          // CRLF → LF 정규화: textarea는 LF만 다루므로 통일
          setContent(d.content.replace(/\r\n/g, "\n"));
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
      onMouseDown={(e) => {
        // 다이얼로그 안에서 드래그를 시작해 바깥에서 떼는 경우 닫히지 않도록
        // mousedown이 오버레이에서 시작됐는지를 기억해 둔다.
        mouseDownOnOverlayRef.current = e.target === e.currentTarget;
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && mouseDownOnOverlayRef.current) {
          onClose();
        }
        mouseDownOnOverlayRef.current = false;
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
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
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
