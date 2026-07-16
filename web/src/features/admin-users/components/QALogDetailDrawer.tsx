"use client";

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchUserQALogDetail,
  type RetrievedDocItem,
  type UserQALogDetail,
} from "@/features/admin-users/api/activity";
import { formatKRW } from "@/lib/format-currency";
import styles from "./QALogDetailDrawer.module.css";

interface Props {
  userId: number;
  qaLogId: number;
  onClose: () => void;
}

const KST_DATETIME = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function fmt(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    return KST_DATETIME.format(new Date(value));
  } catch {
    return value;
  }
}

/**
 * 원화 환산의 근거를 한 줄로 설명한다. 질문분석 상세 드로어(AnswerDetailDrawer)와 동일 표기.
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

function MetaPills({ metadata }: { metadata: Record<string, unknown> }) {
  const entries = Object.entries(metadata || {});
  if (entries.length === 0) return null;
  return (
    <ul className={styles.docMetaList}>
      {entries.map(([k, v]) => (
        <li key={k} className={styles.docMetaItem}>
          <strong>{k}:</strong> {typeof v === "object" ? JSON.stringify(v) : String(v)}
        </li>
      ))}
    </ul>
  );
}

function DocCard({ doc, index }: { doc: RetrievedDocItem; index: number }) {
  return (
    <div className={styles.docCard} data-testid={`retrieved-doc-${index}`}>
      <div className={styles.docHeader}>
        <span className={styles.docIndex}>#{index + 1}</span>
        <MetaPills metadata={doc.metadata} />
      </div>
      <pre className={styles.docContent}>{doc.page_content || "(빈 문서)"}</pre>
    </div>
  );
}

function DetailBody({ detail }: { detail: UserQALogDetail }) {
  return (
    <>
      <section className={styles.section} data-testid="section-question">
        <h3 className={styles.sectionTitle}>원본 질의</h3>
        <p className={styles.blockText}>{detail.question_text || "—"}</p>
      </section>

      <section className={styles.section} data-testid="section-normalized">
        <h3 className={styles.sectionTitle}>① 치환된 문구 (동의어 매칭 결과)</h3>
        {detail.normalized_query ? (
          <p className={`${styles.blockText} ${styles.diffBlock}`}>
            {detail.normalized_query}
          </p>
        ) : (
          <p className={styles.empty}>
            기록 없음 — 본 기능 도입(2026-05-20) 이전 질의이거나 처리 중단됨.
          </p>
        )}
      </section>

      <section className={styles.section} data-testid="section-answer">
        <h3 className={styles.sectionTitle}>② 최종 답변</h3>
        {detail.answer_text ? (
          <p className={`${styles.blockText} ${styles.answerBlock}`}>{detail.answer_text}</p>
        ) : (
          <p className={styles.empty}>답변이 기록되지 않았습니다 ({detail.status ?? "—"}).</p>
        )}
      </section>

      <section className={styles.section} data-testid="section-meta">
        <h3 className={styles.sectionTitle}>메타</h3>
        <div className={styles.metaGrid}>
          <div>
            <span className={styles.metaLabel}>일시</span>
            {fmt(detail.created_at)}
          </div>
          <div>
            <span className={styles.metaLabel}>상태</span>
            {detail.status ?? "—"}
          </div>
          <div>
            <span className={styles.metaLabel}>입력/출력 토큰</span>
            {detail.input_tokens ?? "—"} / {detail.output_tokens ?? "—"}
          </div>
          <div>
            <span className={styles.metaLabel}>처리 시간</span>
            {detail.latency_ms != null ? `${detail.latency_ms} ms` : "—"}
          </div>
          <div>
            <span className={styles.metaLabel}>룰 매칭</span>
            {detail.rule_matched ? "예" : "아니오"}
          </div>
          <div>
            <span className={styles.metaLabel}>비용(USD)</span>
            {detail.cost_usd ?? "—"}
          </div>
          <div>
            <span className={styles.metaLabel}>비용(원화 환산)</span>
            {detail.cost_usd != null ? formatKRW(detail.cost_krw) : "—"}
          </div>
        </div>
        {detail.cost_usd != null && (
          <p className={styles.metaNote}>
            {exchangeRateNote(
              detail.usd_to_krw,
              detail.usd_to_krw_search_date,
              detail.usd_to_krw_updated_at,
            )}
          </p>
        )}
      </section>

      <section className={styles.section} data-testid="section-retrieved-docs">
        <h3 className={styles.sectionTitle}>
          ③ top-k 검색에 들어온 문서 ({detail.retrieved_docs.length}건)
        </h3>
        {detail.rule_matched ? (
          <p className={styles.sectionHint}>
            룰 매칭 경로로 응답된 질의입니다. retriever를 거치지 않으므로 검색 문서가 없습니다.
          </p>
        ) : null}
        {detail.retrieved_docs.length > 0 ? (
          <div className={styles.docList}>
            {detail.retrieved_docs.map((doc, i) => (
              <DocCard key={i} doc={doc} index={i} />
            ))}
          </div>
        ) : !detail.rule_matched ? (
          <p className={styles.empty}>
            검색 문서 기록이 없습니다 (기능 도입 이전 질의일 수 있음).
          </p>
        ) : null}
      </section>

      <section className={styles.section} data-testid="section-prompt">
        <h3 className={styles.sectionTitle}>
          ④ LLM 에 실제로 전달된 프롬프트 (템플릿 + 질문 + 컨텍스트 치환 완료)
        </h3>
        {detail.prompt_text ? (
          <pre className={styles.promptBlock}>{detail.prompt_text}</pre>
        ) : detail.rule_matched ? (
          <p className={styles.empty}>
            룰 매칭 경로 — LLM 호출 없이 응답되어 프롬프트가 없습니다.
          </p>
        ) : (
          <p className={styles.empty}>
            프롬프트 기록이 없습니다 (본 기능 도입 이전 질의이거나 스트림이 중단됨).
          </p>
        )}
      </section>
    </>
  );
}

export function QALogDetailDrawer({ userId, qaLogId, onClose }: Props) {
  const query = useQuery<UserQALogDetail>({
    queryKey: ["admin", "users", userId, "qa-log", qaLogId, "detail"],
    queryFn: () => fetchUserQALogDetail({ userId, qaLogId }),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className={styles.overlay}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="질의 상세"
      data-testid="qa-log-detail-drawer"
    >
      <aside
        className={styles.drawer}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.header}>
          <h2 className={styles.title}>질의 상세 #{qaLogId}</h2>
          <button
            type="button"
            className={styles.closeButton}
            onClick={onClose}
            aria-label="닫기"
            data-testid="qa-log-detail-close"
          >
            ×
          </button>
        </div>
        <div className={styles.body}>
          {query.isError ? (
            <p className={styles.error}>상세 정보를 불러오지 못했습니다.</p>
          ) : query.isLoading || !query.data ? (
            <p className={styles.loading}>불러오는 중…</p>
          ) : (
            <DetailBody detail={query.data} />
          )}
        </div>
      </aside>
    </div>
  );
}
