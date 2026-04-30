"use client";

import Link from "next/link";
import { useId, type ReactNode } from "react";
import styles from "./DashboardWidget.module.css";

export type WidgetTone = "ready" | "coming-soon";

interface DashboardWidgetProps {
  title: string;
  caption?: string;
  tone?: WidgetTone;
  detailHref?: string;
  detailLabel?: string;
  detailDisabledTitle?: string;
  footnote?: string;
  children: ReactNode;
}

export function DashboardWidget({
  title,
  caption,
  tone = "ready",
  detailHref,
  detailLabel = "상세 보기",
  detailDisabledTitle,
  footnote,
  children,
}: DashboardWidgetProps) {
  const titleId = useId();
  const isComingSoon = tone === "coming-soon";

  return (
    <section
      aria-labelledby={titleId}
      className={`${styles.widget} ${isComingSoon ? styles.widgetComingSoon : ""}`}
    >
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <h2 id={titleId} className={styles.title}>
            {title}
          </h2>
          {caption && <p className={styles.caption}>{caption}</p>}
        </div>
        <div className={styles.headerActions}>
          {isComingSoon && (
            <span className={styles.badgeComingSoon} aria-label="준비 중 위젯">
              준비 중
            </span>
          )}
          {detailHref ? (
            <Link
              href={detailHref}
              className={styles.detailLink}
              aria-label={`${title} 상세 페이지로 이동`}
            >
              {detailLabel} →
            </Link>
          ) : (
            isComingSoon &&
            detailDisabledTitle && (
              <span
                className={styles.detailLinkDisabled}
                title={detailDisabledTitle}
                aria-disabled="true"
              >
                상세 준비 중
              </span>
            )
          )}
        </div>
      </header>
      <div className={styles.body}>{children}</div>
      {footnote && <p className={styles.footnote}>{footnote}</p>}
    </section>
  );
}

export function WidgetLoadingState({ message = "로딩 중…" }: { message?: string }) {
  return (
    <div className={styles.stateBox} role="status" aria-live="polite">
      {message}
    </div>
  );
}

export function WidgetErrorState({
  message = "데이터를 불러오지 못했습니다.",
  onRetry,
}: {
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className={`${styles.stateBox} ${styles.stateError}`} role="alert">
      <span>{message}</span>
      {onRetry && (
        <button type="button" className={styles.retryBtn} onClick={onRetry}>
          다시 시도
        </button>
      )}
    </div>
  );
}

export function WidgetEmptyState({ message }: { message: string }) {
  return <div className={styles.stateBox}>{message}</div>;
}
