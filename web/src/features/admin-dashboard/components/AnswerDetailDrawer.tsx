"use client";

import { useEffect, useCallback } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  fetchFeedbackDetail,
  type FeedbackDetail,
  type FeedbackItem,
  type FeedbackRetrievedDoc,
} from "../api/analytics";
import styles from "./AnswerDetailDrawer.module.css";

interface AnswerDetailDrawerProps {
  item: FeedbackItem | null;
  onClose: () => void;
}

export function AnswerDetailDrawer({ item, onClose }: AnswerDetailDrawerProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose]
  );

  useEffect(() => {
    if (!item) return;
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [item, handleKeyDown]);

  const detailQuery = useQuery<FeedbackDetail>({
    queryKey: ["admin", "analytics", "feedback", "detail", item?.qa_log_id],
    queryFn: () => fetchFeedbackDetail(item!.qa_log_id),
    enabled: item !== null,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  if (!item) return null;

  const ratingLabel = item.rating === "good" ? "👍 GOOD" : "👎 BAD";
  const kstFormatted = formatKst(item.created_at);
  const detail = detailQuery.data;

  return (
    <>
      <div
        className={styles.backdrop}
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="답변 상세"
        className={styles.drawer}
      >
        <header className={styles.drawerHeader}>
          <h2 className={styles.drawerTitle}>답변 상세</h2>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            aria-label="Drawer 닫기"
          >
            ✕
          </button>
        </header>

        <div className={styles.drawerBody}>
          <section className={styles.section}>
            <h3 className={styles.sectionLabel}>질문</h3>
            <p className={styles.sectionContent}>{item.question_text}</p>
          </section>

          <section className={styles.section}>
            <h3 className={styles.sectionLabel}>답변</h3>
            <p className={styles.sectionContent}>
              {item.answer_text ?? "—"}
            </p>
          </section>

          <section className={styles.section} aria-labelledby="prompt-label">
            <h3 id="prompt-label" className={styles.sectionLabel}>
              LLM 에 실제로 전달된 프롬프트
            </h3>
            {detailQuery.isLoading ? (
              <p className={styles.promptEmpty}>불러오는 중…</p>
            ) : detail?.prompt_text ? (
              <pre className={styles.promptBlock}>{detail.prompt_text}</pre>
            ) : detail?.rule_matched ? (
              <p className={styles.promptEmpty}>
                룰 매칭 경로 — LLM 호출 없이 응답되어 프롬프트가 없습니다.
              </p>
            ) : (
              <p className={styles.promptEmpty}>
                프롬프트 기록이 없습니다 (본 기능 도입 이전 질의이거나 스트림이 중단됨).
              </p>
            )}
          </section>

          <section className={styles.section} aria-labelledby="topk-label">
            <h3 id="topk-label" className={styles.sectionLabel}>
              top-k 검색 문서{detail ? ` (${detail.retrieved_docs.length}건)` : ""}
            </h3>
            {detailQuery.isLoading ? (
              <p className={styles.topkEmpty}>불러오는 중…</p>
            ) : detailQuery.isError ? (
              <p className={styles.topkEmpty}>
                상세 정보를 불러오지 못했습니다.
              </p>
            ) : detail?.rule_matched ? (
              <p className={styles.topkEmpty}>
                룰 매칭 경로 응답 — retriever를 거치지 않아 검색 문서가 없습니다.
              </p>
            ) : detail && detail.retrieved_docs.length > 0 ? (
              <ol className={styles.docList}>
                {detail.retrieved_docs.map((doc, i) => (
                  <DocCard key={i} doc={doc} index={i} />
                ))}
              </ol>
            ) : (
              <p className={styles.topkEmpty}>
                검색 문서 기록이 없습니다 (기능 도입 이전 질의일 수 있음).
              </p>
            )}
            {detail?.normalized_query ? (
              <details className={styles.normalizedBlock}>
                <summary className={styles.normalizedSummary}>
                  동의어 치환된 검색 쿼리 보기
                </summary>
                <p className={styles.normalizedText}>
                  {detail.normalized_query}
                </p>
              </details>
            ) : null}
          </section>

          <dl className={styles.meta}>
            <div className={styles.metaRow}>
              <dt className={styles.metaLabel}>피드백</dt>
              <dd
                className={`${styles.metaValue} ${
                  item.rating === "good" ? styles.ratingGood : styles.ratingBad
                }`}
              >
                {ratingLabel}
              </dd>
            </div>
            <div className={styles.metaRow}>
              <dt className={styles.metaLabel}>계정</dt>
              <dd className={styles.metaValue}>
                {item.user_id !== null && item.email ? (
                  <Link
                    href={`/admin/users/${item.user_id}`}
                    className={styles.accountLink}
                    title={`${item.email} 고객 관리 페이지로 이동`}
                  >
                    {item.email}
                  </Link>
                ) : (
                  <span className={styles.accountAnon}>비회원</span>
                )}
              </dd>
            </div>
            <div className={styles.metaRow}>
              <dt className={styles.metaLabel}>가입유형</dt>
              <dd className={styles.metaValue}>{item.segment ?? "—"}</dd>
            </div>
            <div className={styles.metaRow}>
              <dt className={styles.metaLabel}>제출일시</dt>
              <dd className={styles.metaValue}>{kstFormatted}</dd>
            </div>
          </dl>
        </div>
      </div>
    </>
  );
}

function DocCard({ doc, index }: { doc: FeedbackRetrievedDoc; index: number }) {
  const entries = Object.entries(doc.metadata ?? {});
  return (
    <li className={styles.docCard}>
      <div className={styles.docHeader}>
        <span className={styles.docIndex}>#{index + 1}</span>
        {entries.length > 0 ? (
          <ul className={styles.docMetaList}>
            {entries.map(([k, v]) => (
              <li key={k} className={styles.docMetaItem}>
                <strong>{k}:</strong>{" "}
                {typeof v === "object" ? JSON.stringify(v) : String(v)}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <pre className={styles.docContent}>{doc.page_content || "(빈 문서)"}</pre>
    </li>
  );
}

function formatKst(iso: string): string {
  try {
    const d = new Date(iso);
    const kst = new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(d);
    return kst;
  } catch {
    return iso;
  }
}
