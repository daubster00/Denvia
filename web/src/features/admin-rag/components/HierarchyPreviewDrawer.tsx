"use client";

import { useEffect } from "react";
import { HierarchyPreviewItem } from "../api/knowledge";
import styles from "./HierarchyPreviewDrawer.module.css";

interface Props {
  open: boolean;
  hierarchy: HierarchyPreviewItem[];
  filename: string;
  chunkCount: number;
  onClose: () => void;
}

export function HierarchyPreviewDrawer({
  open,
  hierarchy,
  filename,
  chunkCount,
  onClose,
}: Props) {
  // Esc 키 닫힘 (UX-DR24)
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      <div
        className={styles.overlay}
        onClick={onClose}
        aria-hidden="true"
        data-testid="drawer-overlay"
      />
      <aside
        className={styles.drawer}
        role="dialog"
        aria-modal="true"
        aria-label="지식 파일 계층 미리보기"
      >
        <div className={styles.header}>
          <div>
            <h2 className={styles.title}>계층 미리보기</h2>
            <p className={styles.subtitle}>
              {filename} · 총 {chunkCount}개 청크
            </p>
          </div>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            aria-label="닫기"
          >
            ✕
          </button>
        </div>

        <div className={styles.body}>
          {hierarchy.length === 0 ? (
            <p className={styles.empty}>계층 정보 없음</p>
          ) : (
            <ul className={styles.treeRoot}>
              {hierarchy.map((cat) => (
                <li key={cat.major}>
                  <details open>
                    <summary className={styles.majorLabel}>{cat.major}</summary>
                    {cat.minors.length > 0 && (
                      <ul className={styles.minorList}>
                        {cat.minors.map((minor, idx) => (
                          <li key={`${minor}-${idx}`} className={styles.minorItem}>
                            {idx < cat.minors.length - 1 ? "├" : "└"} {minor}
                          </li>
                        ))}
                      </ul>
                    )}
                  </details>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className={styles.footer}>
          <button type="button" className={styles.confirmBtn} onClick={onClose}>
            확인
          </button>
        </div>
      </aside>
    </>
  );
}
