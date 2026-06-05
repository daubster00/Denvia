"use client";

/**
 * `/admin/alimtalk/[code]` — 템플릿 상세 페이지.
 *
 * 2026-06-05 모달 → 페이지 분리. 상단: 메타데이터(채널·알리고 코드·수신자·발송 상황·본문 예시).
 * 하단: 페이지 번호 기반 발송 로그 테이블.
 */

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import {
  AdminAlimtalkApiError,
  fetchLogs,
  fetchSummary,
  type AlimtalkLogItem,
  type AlimtalkTemplateStat,
} from "@/features/admin-alimtalk/api";
import { labelForCategory } from "@/features/admin-alimtalk/categoryColors";
import styles from "./page.module.css";

interface PageProps {
  params: Promise<{ code: string }>;
}

type StatusFilter = "all" | "sent" | "failed";

const PER_PAGE = 20;

function _formatKstShort(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const kstMs = d.getTime() + 9 * 60 * 60 * 1000;
  const kst = new Date(kstMs);
  const yyyy = kst.getUTCFullYear();
  const mm = String(kst.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(kst.getUTCDate()).padStart(2, "0");
  const hh = String(kst.getUTCHours()).padStart(2, "0");
  const mi = String(kst.getUTCMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
}

/** 페이지 번호 노출 범위 — 현재 ±2 + 처음/끝, ... 압축. */
function _buildPageWindow(current: number, total: number): (number | "…")[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }
  const result: (number | "…")[] = [];
  const left = Math.max(2, current - 2);
  const right = Math.min(total - 1, current + 2);
  result.push(1);
  if (left > 2) result.push("…");
  for (let i = left; i <= right; i++) result.push(i);
  if (right < total - 1) result.push("…");
  result.push(total);
  return result;
}

export default function AdminAlimtalkDetailPage({ params }: PageProps) {
  const { code: codeRaw } = use(params);
  const templateCode = decodeURIComponent(codeRaw);

  const [template, setTemplate] = useState<AlimtalkTemplateStat | null>(null);
  const [templateLoading, setTemplateLoading] = useState(true);
  const [templateError, setTemplateError] = useState<string | null>(null);

  const [logs, setLogs] = useState<AlimtalkLogItem[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<StatusFilter>("all");
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);

  // 1) 템플릿 메타 — summary에서 찾기.
  useEffect(() => {
    const ctrl = new AbortController();
    setTemplateLoading(true);
    setTemplateError(null);
    fetchSummary(ctrl.signal)
      .then((data) => {
        const found = data.templates.find((t) => t.template_code === templateCode);
        if (!found) {
          setTemplateError(
            "해당 템플릿을 찾을 수 없습니다. 코드가 올바른지 확인해주세요.",
          );
          setTemplate(null);
        } else {
          setTemplate(found);
        }
      })
      .catch((err) => {
        if (ctrl.signal.aborted) return;
        const e = err as AdminAlimtalkApiError;
        setTemplateError(e?.message ?? "템플릿 정보를 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setTemplateLoading(false);
      });
    return () => ctrl.abort();
  }, [templateCode]);

  // 2) 로그 — page 모드.
  const loadLogs = useCallback(
    (nextPage: number, nextStatus: StatusFilter, signal?: AbortSignal) => {
      setLogsLoading(true);
      setLogsError(null);
      return fetchLogs(
        {
          template_code: templateCode,
          status: nextStatus,
          page: nextPage,
          per_page: PER_PAGE,
        },
        signal,
      )
        .then((data) => {
          setLogs(data.items);
          setTotal(data.total ?? 0);
          setTotalPages(data.total_pages ?? 1);
        })
        .catch((err) => {
          if (signal?.aborted) return;
          const e = err as AdminAlimtalkApiError;
          setLogsError(e?.message ?? "로그를 불러오지 못했습니다.");
        })
        .finally(() => {
          if (!signal?.aborted) setLogsLoading(false);
        });
    },
    [templateCode],
  );

  useEffect(() => {
    const ctrl = new AbortController();
    void loadLogs(page, status, ctrl.signal);
    return () => ctrl.abort();
  }, [loadLogs, page, status]);

  // status가 바뀌면 1페이지로
  function onChangeStatus(next: StatusFilter) {
    setStatus(next);
    setPage(1);
  }

  function goToPage(next: number) {
    if (next < 1 || next > totalPages || next === page) return;
    setPage(next);
  }

  const pageWindow = _buildPageWindow(page, totalPages);

  return (
    <main className={styles.page} aria-labelledby="alimtalkDetailTitle">
      <div className={styles.breadcrumb}>
        <Link href="/admin/alimtalk" className={styles.backLink}>
          ← 알림톡 관리
        </Link>
      </div>

      {templateLoading ? (
        <div className={styles.loadingBox}>불러오는 중…</div>
      ) : templateError ? (
        <div className={styles.invalidBox} role="alert">
          {templateError}
        </div>
      ) : template ? (
        <>
          <header className={styles.header}>
            <div className={styles.headerChips}>
              <span
                className={styles.channelChip}
                data-channel={template.channel}
              >
                {template.channel === "sms" ? "SMS" : "알림톡"}
              </span>
              <span className={styles.chip} data-category={template.category}>
                {labelForCategory(template.category)}
              </span>
            </div>
            <h1 id="alimtalkDetailTitle" className={styles.title}>
              {template.channel === "sms"
                ? template.template_code
                : template.aligo_tpl_code ?? "(미등록)"}
            </h1>
            <p className={styles.subtitle}>{template.title}</p>
          </header>

          {/* 메타데이터 */}
          <section className={styles.metaCard} aria-label="템플릿 정보">
            <dl className={styles.metaGrid}>
              <dt>알리고 코드</dt>
              <dd>
                {template.channel === "sms"
                  ? "—  (SMS는 알리고 콘솔 등록 없이 자유 텍스트로 발송)"
                  : template.aligo_tpl_code ?? "미등록"}
              </dd>
              <dt>내부 코드</dt>
              <dd className={styles.metaMono}>{template.template_code}</dd>
              <dt>수신자</dt>
              <dd>
                {template.recipient_kind === "admin"
                  ? "관리자 (admin@denvia.ai.kr)"
                  : "일반 사용자"}
              </dd>
              <dt>발송 상황</dt>
              <dd>{template.trigger_situation}</dd>
            </dl>
          </section>

          {/* 본문 예시 */}
          <section className={styles.bodySection} aria-label="본문 예시">
            <h2 className={styles.sectionTitle}>본문 예시</h2>
            <pre className={styles.bodyPre}>{template.body_example}</pre>
          </section>

          {/* 발송 로그 */}
          <section className={styles.logsSection} aria-label="발송 로그">
            <div className={styles.logsHeader}>
              <h2 className={styles.sectionTitle}>
                발송 로그
                {total > 0 && (
                  <span className={styles.totalCount}> · 총 {total}건</span>
                )}
              </h2>
              <div className={styles.filterRow}>
                <label className={styles.filterLabel} htmlFor="logStatusFilter">
                  상태
                </label>
                <select
                  id="logStatusFilter"
                  className={styles.filterSelect}
                  value={status}
                  onChange={(e) => onChangeStatus(e.target.value as StatusFilter)}
                  disabled={logsLoading}
                >
                  <option value="all">전체</option>
                  <option value="sent">성공</option>
                  <option value="failed">실패</option>
                </select>
              </div>
            </div>

            {logsError ? (
              <div className={styles.invalidBox} role="alert">
                {logsError}
              </div>
            ) : logs.length === 0 && !logsLoading ? (
              <div className={styles.emptyState}>발송 로그가 없습니다.</div>
            ) : (
              <div className={styles.tableWrap}>
                <table className={styles.logTable}>
                  <thead>
                    <tr>
                      <th>접수 시각 (KST)</th>
                      <th>종류</th>
                      <th>발송 시각 (KST)</th>
                      <th>대상 user_id</th>
                      <th>마스킹 번호</th>
                      <th>상태</th>
                      <th>시도</th>
                      <th>오류</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map((item) => (
                      <tr key={item.id}>
                        <td>{_formatKstShort(item.created_at)}</td>
                        <td>
                          <span
                            className={styles.kindChip}
                            data-kind={item.is_test ? "test" : "prod"}
                          >
                            {item.is_test ? "테스트" : "운영"}
                          </span>
                        </td>
                        <td>
                          {item.sent_at ? _formatKstShort(item.sent_at) : "-"}
                        </td>
                        <td>{item.user_id ?? "-"}</td>
                        <td>{item.phone_masked ?? "-"}</td>
                        <td>
                          <span
                            className={styles.logStatus}
                            data-status={item.status}
                          >
                            {item.status === "sent" ? "성공" : "실패"}
                          </span>
                        </td>
                        <td>{item.attempts}</td>
                        <td>
                          <span
                            className={styles.logError}
                            title={item.last_error ?? ""}
                          >
                            {item.last_error ?? "-"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {totalPages > 1 && (
              <nav className={styles.pagination} aria-label="페이지 네비게이션">
                <button
                  type="button"
                  className={styles.pageBtn}
                  onClick={() => goToPage(page - 1)}
                  disabled={page <= 1 || logsLoading}
                >
                  이전
                </button>
                {pageWindow.map((p, idx) =>
                  p === "…" ? (
                    <span
                      key={`gap-${idx}`}
                      className={styles.pageGap}
                      aria-hidden="true"
                    >
                      …
                    </span>
                  ) : (
                    <button
                      key={p}
                      type="button"
                      className={styles.pageBtn}
                      data-active={p === page ? "true" : undefined}
                      onClick={() => goToPage(p)}
                      disabled={logsLoading}
                      aria-current={p === page ? "page" : undefined}
                    >
                      {p}
                    </button>
                  ),
                )}
                <button
                  type="button"
                  className={styles.pageBtn}
                  onClick={() => goToPage(page + 1)}
                  disabled={page >= totalPages || logsLoading}
                >
                  다음
                </button>
              </nav>
            )}
          </section>
        </>
      ) : null}
    </main>
  );
}
