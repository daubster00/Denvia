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

interface Props {
  onSuccess: (resp: UploadKnowledgeResponse) => void;
  onHighlightDuplicate?: (id: number) => void;
}

export function UploadDropzone({ onSuccess, onHighlightDuplicate }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [retryFile, setRetryFile] = useState<File | null>(null);

  const handleFile = async (file: File) => {
    setError(null);
    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      return;
    }

    setRetryFile(file);
    setProgress(0);
    try {
      const resp = await uploadKnowledge(file, setProgress);
      setProgress(null);
      onSuccess(resp);
    } catch (err: unknown) {
      setProgress(null);
      const e = err as { code?: string; message?: string; details?: { existing_upload_id?: number }; status?: number };
      if (e.code === "UPLOAD_DUPLICATE" && e.details?.existing_upload_id) {
        setError(`이미 동일한 내용의 파일이 있습니다(ID: ${e.details.existing_upload_id})`);
        onHighlightDuplicate?.(e.details.existing_upload_id);
      } else if (e.status === 429) {
        setError("잠시 후 다시 시도해주세요. (분당 5회 제한)");
      } else {
        setError(e.message ?? "업로드에 실패했습니다. 다시 시도해주세요.");
      }
    }
  };

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = "";
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      inputRef.current?.click();
    }
  };

  return (
    <div className={styles.wrapper}>
      {error && (
        <div className={styles.errorMessage} role="alert">
          {error}
          {retryFile && (
            <button
              type="button"
              className={styles.retryBtn}
              onClick={() => {
                setError(null);
                if (retryFile) handleFile(retryFile);
              }}
            >
              재시도
            </button>
          )}
        </div>
      )}

      <div
        role="button"
        tabIndex={0}
        aria-label="TXT 파일 업로드 영역. 클릭하거나 파일을 끌어다 놓으세요."
        className={`${styles.dropzone} ${isDragOver ? styles.dragOver : ""} ${progress !== null ? styles.uploading : ""}`}
        onClick={() => inputRef.current?.click()}
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
          className={styles.hiddenInput}
          onChange={onInputChange}
          aria-hidden="true"
          tabIndex={-1}
        />
        {progress !== null ? (
          <div className={styles.progressWrapper}>
            <div className={styles.progressBar} style={{ width: `${progress}%` }} />
            <span className={styles.progressText}>{Math.round(progress)}%</span>
          </div>
        ) : (
          <>
            <span className={styles.icon}>📂</span>
            <p className={styles.hint}>클릭하거나 파일을 여기에 끌어다 놓으세요</p>
            <p className={styles.subHint}>.txt 파일 · 최대 10MB</p>
          </>
        )}
      </div>
    </div>
  );
}
