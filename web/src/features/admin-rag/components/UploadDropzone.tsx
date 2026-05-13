"use client";

import { useRef, useState } from "react";
import { uploadKnowledge, UploadKnowledgeResponse } from "../api/knowledge";
import styles from "./UploadDropzone.module.css";

const MAX_BYTES = 10 * 1024 * 1024;

function validateFile(file: File): string | null {
  if (file.size > MAX_BYTES) return "파일이 10MB를 초과합니다.";
  if (!file.name.toLowerCase().endsWith(".txt")) return "확장자가 .txt가 아닙니다.";
  const mime = file.type;
  if (mime && mime !== "text/plain" && mime !== "") return "텍스트 파일(.txt)만 업로드 가능합니다.";
  return null;
}

type ItemStatus = "pending" | "uploading" | "success" | "error";

interface FileItem {
  id: string;
  file: File;
  status: ItemStatus;
  progress: number;
  error?: string;
}

interface Props {
  onSuccess: (resp: UploadKnowledgeResponse) => void;
  onHighlightDuplicate?: (id: number) => void;
}

let _seq = 0;
const nextId = () => `f-${++_seq}-${Date.now()}`;

export function UploadDropzone({ onSuccess, onHighlightDuplicate }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [items, setItems] = useState<FileItem[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  const updateItem = (id: string, patch: Partial<FileItem>) => {
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...patch } : it)));
  };

  const uploadOne = async (item: FileItem): Promise<UploadKnowledgeResponse | null> => {
    updateItem(item.id, { status: "uploading", progress: 0, error: undefined });
    try {
      const resp = await uploadKnowledge(item.file, (pct) =>
        updateItem(item.id, { progress: pct }),
      );
      updateItem(item.id, { status: "success", progress: 100 });
      return resp;
    } catch (err: unknown) {
      const e = err as {
        code?: string;
        message?: string;
        details?: { existing_upload_id?: number };
        status?: number;
      };
      let msg = e.message ?? "업로드에 실패했습니다.";
      if (e.code === "UPLOAD_DUPLICATE" && e.details?.existing_upload_id) {
        msg = `이미 동일한 내용의 파일이 있습니다(ID: ${e.details.existing_upload_id})`;
        onHighlightDuplicate?.(e.details.existing_upload_id);
      } else if (e.status === 429) {
        msg = "잠시 후 다시 시도해주세요. (분당 5회 제한)";
      }
      updateItem(item.id, { status: "error", error: msg });
      return null;
    }
  };

  const runQueue = async (queue: FileItem[]) => {
    setIsUploading(true);
    let lastSuccess: UploadKnowledgeResponse | null = null;
    for (const item of queue) {
      if (item.status === "error") continue;
      const resp = await uploadOne(item);
      if (resp) lastSuccess = resp;
    }
    setIsUploading(false);
    if (lastSuccess) onSuccess(lastSuccess);
  };

  const handleFiles = (files: File[]) => {
    if (files.length === 0) return;
    const newItems: FileItem[] = files.map((file) => {
      const err = validateFile(file);
      return {
        id: nextId(),
        file,
        status: err ? "error" : "pending",
        progress: 0,
        error: err ?? undefined,
      };
    });
    setItems((prev) => [...prev, ...newItems]);
    void runQueue(newItems);
  };

  const retryItem = async (id: string) => {
    const target = items.find((it) => it.id === id);
    if (!target) return;
    const validationErr = validateFile(target.file);
    if (validationErr) {
      updateItem(id, { status: "error", error: validationErr });
      return;
    }
    setIsUploading(true);
    const resp = await uploadOne(target);
    setIsUploading(false);
    if (resp) onSuccess(resp);
  };

  const removeItem = (id: string) => {
    setItems((prev) => prev.filter((it) => it.id !== id));
  };

  const clearCompleted = () => {
    setItems((prev) => prev.filter((it) => it.status !== "success"));
  };

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const fs = Array.from(e.target.files ?? []);
    if (fs.length > 0) handleFiles(fs);
    e.target.value = "";
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const fs = Array.from(e.dataTransfer.files);
    if (fs.length > 0) handleFiles(fs);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (!isUploading) inputRef.current?.click();
    }
  };

  const successCount = items.filter((it) => it.status === "success").length;
  const errorCount = items.filter((it) => it.status === "error").length;
  const hasItems = items.length > 0;

  return (
    <div className={styles.wrapper}>
      <div
        role="button"
        tabIndex={0}
        aria-label="TXT 파일 업로드 영역. 클릭하거나 파일을 끌어다 놓으세요. 여러 파일 선택 가능."
        className={`${styles.dropzone} ${isDragOver ? styles.dragOver : ""} ${isUploading ? styles.uploading : ""}`}
        onClick={() => {
          if (!isUploading) inputRef.current?.click();
        }}
        onKeyDown={onKeyDown}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".txt,text/plain"
          multiple
          className={styles.hiddenInput}
          onChange={onInputChange}
          aria-hidden="true"
          tabIndex={-1}
        />
        <span className={styles.icon} aria-hidden="true">📂</span>
        <p className={styles.hint}>클릭하거나 파일을 여기에 끌어다 놓으세요</p>
        <p className={styles.subHint}>.txt 파일 · 최대 10MB · 여러 파일 선택 가능 (분당 5건 권장)</p>
      </div>

      {hasItems && (
        <div className={styles.fileList} role="list" aria-label="업로드 파일 목록">
          {items.map((it) => (
            <div key={it.id} className={styles.fileItem} role="listitem">
              <div className={styles.fileInfo}>
                <span className={styles.fileName} title={it.file.name}>{it.file.name}</span>
                <span className={styles.fileMeta}>
                  {(it.file.size / 1024).toFixed(1)} KB
                </span>
              </div>

              <div className={styles.fileStatus}>
                {it.status === "pending" && (
                  <span className={styles.statusPending}>대기 중</span>
                )}
                {it.status === "uploading" && (
                  <div className={styles.itemProgressWrap} aria-label="업로드 진행률">
                    <div className={styles.itemProgressTrack}>
                      <div
                        className={styles.itemProgressBar}
                        style={{ width: `${it.progress}%` }}
                      />
                    </div>
                    <span className={styles.itemProgressText}>{Math.round(it.progress)}%</span>
                  </div>
                )}
                {it.status === "success" && (
                  <span className={styles.statusSuccess}>완료</span>
                )}
                {it.status === "error" && (
                  <span className={styles.statusError} role="alert">{it.error}</span>
                )}
              </div>

              <div className={styles.fileActions}>
                {it.status === "error" && (
                  <button
                    type="button"
                    className={styles.retryBtn}
                    onClick={() => retryItem(it.id)}
                    disabled={isUploading}
                  >
                    재시도
                  </button>
                )}
                {it.status !== "uploading" && (
                  <button
                    type="button"
                    className={styles.removeBtn}
                    onClick={() => removeItem(it.id)}
                    aria-label={`${it.file.name} 목록에서 제거`}
                    disabled={isUploading}
                  >
                    ×
                  </button>
                )}
              </div>
            </div>
          ))}

          {!isUploading && (successCount > 0 || errorCount > 0) && (
            <div className={styles.summaryBar}>
              <span className={styles.summaryText}>
                총 {items.length}개 · 완료 {successCount}개
                {errorCount > 0 ? ` · 실패 ${errorCount}개` : ""}
              </span>
              {successCount > 0 && (
                <button
                  type="button"
                  className={styles.clearBtn}
                  onClick={clearCompleted}
                >
                  완료 항목 지우기
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
