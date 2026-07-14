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
import { formatKRW } from "@/lib/format-currency";
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
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = prevOverflow;
    };
  }, [item, handleKeyDown]);

  const detailQuery = useQuery<FeedbackDetail>({
    queryKey: ["admin", "analytics", "feedback", "detail", item?.qa_log_id],
    queryFn: () => fetchFeedbackDetail(item!.qa_log_id),
    enabled: item !== null,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  if (!item) return null;

  const detail = detailQuery.data;
  // 원본 질의·최종 답변은 목록 item 에 이미 있어 상세 로드 전에도 즉시 보여준다.
  const questionText = detail?.question_text ?? item.question_text;
  const answerText = detail?.answer_text ?? item.answer_text;
  const createdAt = detail?.created_at ?? item.created_at;

  return (
    <div
      className={styles.detailBackdrop}
      role="dialog"
      aria-modal="true"
      aria-label="답변 상세"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className={styles.detailDrawer}>
        <div className={styles.detailPanel}>
          <header className={styles.detailHeader}>
            <h3 className={styles.detailTitle}>
              답변 상세 #{item.qa_log_id}
            </h3>
            <button
              type="button"
              className={styles.detailClose}
              onClick={onClose}
              aria-label="상세 패널 닫기"
            >
              ×
            </button>
          </header>

          <div className={styles.detailBody}>
            {/* ① 원본 질의 */}
            <section
              className={styles.detailSection}
              data-testid="section-question"
            >
              <h4 className={styles.detailSectionTitle}>원본 질의</h4>
              <p className={styles.detailBlockText}>{questionText || "—"}</p>
            </section>

            {/* ② 치환된 문구 */}
            <section
              className={styles.detailSection}
              data-testid="section-normalized"
            >
              <h4 className={styles.detailSectionTitle}>
                ① 치환된 문구 (동의어 매칭 결과)
              </h4>
              {detailQuery.isLoading ? (
                <p className={styles.detailLoading} role="status">
                  불러오는 중…
                </p>
              ) : detail?.normalized_query ? (
                <p
                  className={`${styles.detailBlockText} ${styles.detailDiffBlock}`}
                >
                  {detail.normalized_query}
                </p>
              ) : (
                <p className={styles.detailEmpty}>
                  기록 없음 — 본 기능 도입(2026-05-20) 이전 질의이거나 처리
                  중단됨.
                </p>
              )}
            </section>

            {/* ③ 최종 답변 */}
            <section
              className={styles.detailSection}
              data-testid="section-answer"
            >
              <h4 className={styles.detailSectionTitle}>② 최종 답변</h4>
              {answerText ? (
                <p
                  className={`${styles.detailBlockText} ${styles.detailAnswerBlock}`}
                >
                  {answerText}
                </p>
              ) : (
                <p className={styles.detailEmpty}>
                  답변이 기록되지 않았습니다 ({detail?.status ?? "—"}).
                </p>
              )}
            </section>

            {/* ④ 메타 */}
            <section
              className={styles.detailSection}
              data-testid="section-meta"
            >
              <h4 className={styles.detailSectionTitle}>메타</h4>
              <div className={styles.detailMetaGrid}>
                <div>
                  <span className={styles.detailMetaLabel}>피드백</span>
                  <span
                    className={
                      item.rating === "good"
                        ? styles.ratingGood
                        : styles.ratingBad
                    }
                  >
                    {item.rating === "good" ? "👍 GOOD" : "👎 BAD"}
                  </span>
                </div>
                <div>
                  <span className={styles.detailMetaLabel}>계정</span>
                  {item.user_id !== null && item.email ? (
                    <Link
                      href={`/admin/users/${item.user_id}`}
                      className={styles.accountLink}
                      title={`${item.email} 고객 관리 페이지로 이동`}
                    >
                      {item.email}
                    </Link>
                  ) : (
                    <span className={styles.accountAnon}>탈퇴회원</span>
                  )}
                </div>
                <div>
                  <span className={styles.detailMetaLabel}>가입유형</span>
                  {segmentLabel(item.segment)}
                </div>
                <div>
                  <span className={styles.detailMetaLabel}>일시</span>
                  {formatDateTime(createdAt)}
                </div>
                <div>
                  <span className={styles.detailMetaLabel}>상태</span>
                  {detail?.status ?? "—"}
                </div>
                <div>
                  <span className={styles.detailMetaLabel}>입력/출력 토큰</span>
                  {detail?.input_tokens ?? "—"} / {detail?.output_tokens ?? "—"}
                </div>
                <div>
                  <span className={styles.detailMetaLabel}>처리 시간</span>
                  {detail?.latency_ms != null ? `${detail.latency_ms} ms` : "—"}
                </div>
                <div>
                  <span className={styles.detailMetaLabel}>룰 매칭</span>
                  {detail ? (detail.rule_matched ? "예" : "아니오") : "—"}
                </div>
                <div>
                  <span className={styles.detailMetaLabel}>비용(USD)</span>
                  {detail?.cost_usd ?? "—"}
                </div>
                <div>
                  <span className={styles.detailMetaLabel}>비용(원화 환산)</span>
                  {detail?.cost_usd != null ? formatKRW(detail.cost_krw) : "—"}
                </div>
              </div>
              {detail?.cost_usd != null && (
                <p className={styles.detailMetaNote}>
                  {exchangeRateNote(
                    detail.usd_to_krw,
                    detail.usd_to_krw_search_date,
                    detail.usd_to_krw_updated_at,
                  )}
                </p>
              )}
            </section>

            {/* ⑤ top-k 검색 문서 */}
            <section
              className={styles.detailSection}
              data-testid="section-retrieved-docs"
            >
              <h4 className={styles.detailSectionTitle}>
                ③ top-k 검색에 들어온 문서
                {detail ? ` (${detail.retrieved_docs.length}건)` : ""}
              </h4>
              {detailQuery.isLoading ? (
                <p className={styles.detailLoading} role="status">
                  불러오는 중…
                </p>
              ) : detailQuery.isError ? (
                <section className={styles.errorBox} role="alert">
                  <p>상세 정보를 불러오지 못했습니다.</p>
                  <button
                    type="button"
                    className={styles.retryBtn}
                    onClick={() => detailQuery.refetch()}
                  >
                    다시 시도
                  </button>
                </section>
              ) : detail?.rule_matched ? (
                <p className={styles.detailSectionHint}>
                  룰 매칭 경로로 응답된 질의입니다. retriever를 거치지 않으므로
                  검색 문서가 없습니다.
                </p>
              ) : detail && detail.retrieved_docs.length > 0 ? (
                <div className={styles.detailDocList}>
                  {detail.retrieved_docs.map((doc, idx) => (
                    <DocCard key={idx} doc={doc} index={idx} />
                  ))}
                </div>
              ) : (
                <p className={styles.detailEmpty}>
                  검색 문서 기록이 없습니다 (기능 도입 이전 질의일 수 있음).
                </p>
              )}
            </section>

            {/* ⑥ LLM 프롬프트 */}
            <section
              className={styles.detailSection}
              data-testid="section-prompt"
            >
              <h4 className={styles.detailSectionTitle}>
                ④ LLM 에 실제로 전달된 프롬프트 (템플릿 + 질문 + 컨텍스트 치환
                완료)
              </h4>
              {detailQuery.isLoading ? (
                <p className={styles.detailLoading} role="status">
                  불러오는 중…
                </p>
              ) : detail?.prompt_text ? (
                <pre className={styles.detailPromptBlock}>
                  {detail.prompt_text}
                </pre>
              ) : detail?.rule_matched ? (
                <p className={styles.detailEmpty}>
                  룰 매칭 경로 — LLM 호출 없이 응답되어 프롬프트가 없습니다.
                </p>
              ) : (
                <p className={styles.detailEmpty}>
                  프롬프트 기록이 없습니다 (본 기능 도입 이전 질의이거나
                  스트림이 중단됨).
                </p>
              )}
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}

function DocCard({ doc, index }: { doc: FeedbackRetrievedDoc; index: number }) {
  const entries = Object.entries(doc.metadata ?? {});
  return (
    <div className={styles.detailDocCard} data-testid={`retrieved-doc-${index}`}>
      <div className={styles.detailDocHeader}>
        <span className={styles.detailDocIndex}>#{index + 1}</span>
        {entries.length > 0 ? (
          <ul className={styles.detailDocMetaList}>
            {entries.map(([k, v]) => (
              <li key={k} className={styles.detailDocMetaItem}>
                <strong>{k}:</strong>{" "}
                {typeof v === "object" ? JSON.stringify(v) : String(v)}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <pre className={styles.detailDocContent}>
        {doc.page_content || "(빈 문서)"}
      </pre>
    </div>
  );
}

function segmentLabel(seg: string | null): string {
  if (!seg) return "—";
  if (seg === "doctor") return "치과의사";
  if (seg === "hygienist") return "치과위생사";
  if (seg === "student_other") return "학생/기타";
  return seg;
}

function formatDateTime(iso: string): string {
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso;
  const yyyy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dd = String(dt.getDate()).padStart(2, "0");
  const hh = String(dt.getHours()).padStart(2, "0");
  const mi = String(dt.getMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
}

/**
 * 원화 환산의 근거를 한 줄로 설명한다. questions 상세 패널과 동일한 표기.
 */
function exchangeRateNote(
  usdToKrw: number,
  searchDate: string | null,
  updatedAt: string | null,
): string {
  const base = `환율 기준: 1 USD = ${formatKRW(usdToKrw)}`;
  const parts: string[] = [];
  if (searchDate) parts.push(`${searchDate} 환율`);
  if (updatedAt) {
    const dt = new Date(updatedAt);
    if (!Number.isNaN(dt.getTime())) {
      const mm = String(dt.getMonth() + 1).padStart(2, "0");
      const dd = String(dt.getDate()).padStart(2, "0");
      const hh = String(dt.getHours()).padStart(2, "0");
      const mi = String(dt.getMinutes()).padStart(2, "0");
      parts.push(`${mm}-${dd} ${hh}:${mi} 갱신`);
    }
  }
  if (parts.length === 0) return `${base} (기본 적용 환율)`;
  return `${base} (${parts.join(", ")})`;
}
