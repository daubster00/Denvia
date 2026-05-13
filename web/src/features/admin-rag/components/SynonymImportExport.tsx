"use client";

import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  buildExportUrl,
  importSynonymCsv,
  type ImportConflict,
  type ImportPreviewResponse,
  type ImportSummary,
} from "../api/synonyms";
import styles from "./SynonymImportExport.module.css";

export function SynonymImportExport() {
  const [modalOpen, setModalOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [errorText, setErrorText] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const qc = useQueryClient();

  const dryRun = useMutation({
    mutationFn: (f: File) => importSynonymCsv(f, true),
    onSuccess: (data) => {
      setPreview(data);
      setErrorText(null);
    },
    onError: (err: unknown) => {
      setPreview(null);
      setErrorText(humanizeImportError(err));
    },
  });

  const apply = useMutation({
    mutationFn: (f: File) => importSynonymCsv(f, false),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-rag-synonyms"] });
      closeModal();
    },
    onError: (err: unknown) => {
      const e = err as Error & {
        summary?: ImportSummary;
        conflicts?: ImportConflict[];
      };
      if (e?.message === "IMPORT_HAS_CONFLICTS" && e.summary && e.conflicts) {
        setPreview({
          summary: e.summary,
          conflicts: e.conflicts,
          invalid: [],
        });
        setErrorText("충돌이 있어 적용이 중단되었습니다. CSV를 수정해 다시 시도해 주세요.");
      } else {
        setErrorText(humanizeImportError(err));
      }
    },
  });

  const closeModal = () => {
    setModalOpen(false);
    setFile(null);
    setPreview(null);
    setErrorText(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setPreview(null);
    setErrorText(null);
  };

  const handleDryRun = () => {
    if (!file) return;
    dryRun.mutate(file);
  };

  const handleApply = () => {
    if (!file) return;
    apply.mutate(file);
  };

  return (
    <>
      <div className={styles.actionBar}>
        <button type="button" className={styles.btn} onClick={() => setModalOpen(true)}>
          CSV 가져오기
        </button>
        <a className={styles.linkBtn} href={buildExportUrl()}>
          CSV 내보내기
        </a>
      </div>

      {modalOpen && (
        <div
          className={styles.backdrop}
          onClick={(e) => {
            if (e.target === e.currentTarget && !apply.isPending) closeModal();
          }}
        >
          <div className={styles.modal} role="dialog" aria-labelledby="csv-modal-title">
            <h2 id="csv-modal-title" className={styles.modalTitle}>
              CSV 일괄 가져오기
            </h2>
            <p className={styles.modalDesc}>
              형식: <code>canonical_term,synonyms</code> (동의어는 <code>|</code> 로 구분)
            </p>

            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,text/csv"
              onChange={onFileChange}
              className={styles.fileInput}
            />

            {file && !preview && !errorText && (
              <button
                type="button"
                className={styles.btn}
                onClick={handleDryRun}
                disabled={dryRun.isPending}
              >
                {dryRun.isPending ? "검사 중..." : "미리보기 (Dry-Run)"}
              </button>
            )}

            {errorText && <p className={styles.error}>{errorText}</p>}

            {preview && <ImportPreviewSummary preview={preview} />}

            <div className={styles.modalActions}>
              <button
                type="button"
                className={styles.cancelBtn}
                onClick={closeModal}
                disabled={apply.isPending}
              >
                닫기
              </button>
              {preview && preview.summary.conflicts === 0 && preview.summary.invalid === 0 && (
                <button
                  type="button"
                  className={styles.primaryBtn}
                  onClick={handleApply}
                  disabled={apply.isPending}
                >
                  {apply.isPending ? "적용 중..." : "적용"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function ImportPreviewSummary({ preview }: { preview: ImportPreviewResponse }) {
  const { summary, conflicts, invalid } = preview;
  return (
    <div className={styles.summaryBox}>
      <div className={styles.summaryRow}>
        <span>신규 생성</span>
        <strong>{summary.to_create}</strong>
      </div>
      <div className={styles.summaryRow}>
        <span>업데이트</span>
        <strong>{summary.to_update}</strong>
      </div>
      <div className={styles.summaryRow}>
        <span>변경 없음</span>
        <strong>{summary.unchanged}</strong>
      </div>
      <div className={styles.summaryRow}>
        <span>충돌</span>
        <strong className={summary.conflicts > 0 ? styles.warnText : ""}>
          {summary.conflicts}
        </strong>
      </div>
      <div className={styles.summaryRow}>
        <span>잘못된 행</span>
        <strong className={summary.invalid > 0 ? styles.warnText : ""}>
          {summary.invalid}
        </strong>
      </div>

      {conflicts.length > 0 && (
        <details className={styles.details}>
          <summary>충돌 상세 ({conflicts.length}건)</summary>
          <ul className={styles.detailsList}>
            {conflicts.slice(0, 30).map((c) => (
              <li key={`${c.row}-${c.canonical_term}`}>
                {c.row}행 — {c.canonical_term} : {c.reason}
              </li>
            ))}
            {conflicts.length > 30 && <li>... 외 {conflicts.length - 30}건</li>}
          </ul>
        </details>
      )}

      {invalid.length > 0 && (
        <details className={styles.details}>
          <summary>잘못된 행 상세 ({invalid.length}건)</summary>
          <ul className={styles.detailsList}>
            {invalid.slice(0, 30).map((i) => (
              <li key={`${i.row}`}>
                {i.row}행 — {i.error}
              </li>
            ))}
            {invalid.length > 30 && <li>... 외 {invalid.length - 30}건</li>}
          </ul>
        </details>
      )}
    </div>
  );
}

function humanizeImportError(err: unknown): string {
  const message = err instanceof Error ? err.message : String(err);
  switch (message) {
    case "IMPORT_HEADER_INVALID":
      return "CSV 헤더가 canonical_term,synonyms 이어야 합니다.";
    case "IMPORT_FILE_TOO_LARGE":
      return "파일이 너무 큽니다 (최대 1MB).";
    case "IMPORT_TOO_MANY_ROWS":
      return "행이 너무 많습니다 (최대 5000행).";
    case "IMPORT_CONTENT_TYPE_INVALID":
      return "CSV 파일만 업로드 가능합니다.";
    default:
      return "가져오기에 실패했습니다.";
  }
}
