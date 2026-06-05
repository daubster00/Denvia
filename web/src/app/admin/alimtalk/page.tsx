"use client";

/**
 * Story 4.6 — `/admin/alimtalk` 관리자 알림톡 관리 페이지.
 *
 * 3섹션 레이아웃:
 * 1. 테스트 수신 번호 카드 (SSOT 1곳)
 * 2. 요약 카드 3종 (오늘 / 이번 달 / 실패율)
 * 3. 카탈로그 테이블 + 행별 테스트 발송·상세보기 (알림톡 + SMS 통합)
 *
 * 좌측 정렬 1300px 상한, 인라인 CSS 0건.
 * 🚫 공지(notice) 카테고리는 백엔드 admin_catalog가 제외 — UI 노출 금지.
 */

import { useCallback, useEffect, useState } from "react";
import { useAdminSessionStore } from "@/stores/admin-session-store";
import {
  AdminAlimtalkApiError,
  fetchSummary,
  getTestRecipient,
  type AlimtalkSummary,
  type TestRecipient,
} from "@/features/admin-alimtalk/api";
import { TestRecipientCard } from "./TestRecipientCard";
import { TemplateRow } from "./TemplateRow";
import styles from "./page.module.css";

interface ToastEntry {
  id: number;
  tone: "success" | "error" | "warn" | "info";
  message: string;
}

let _toastSeq = 1;

export default function AdminAlimtalkPage() {
  const admin = useAdminSessionStore((s) => s.admin);
  const adminGrade = admin?.admin_grade ?? null;
  const canEditRecipient = adminGrade === "master" || adminGrade === "operator" || adminGrade === null;
  const canTestSend = adminGrade !== "pending";

  const [summary, setSummary] = useState<AlimtalkSummary | null>(null);
  const [recipient, setRecipient] = useState<TestRecipient | null>(null);
  const [toasts, setToasts] = useState<ToastEntry[]>([]);
  const [quotaReached, setQuotaReached] = useState(false);
  const [loading, setLoading] = useState(true);

  const pushToast = useCallback(
    (tone: "success" | "error" | "warn", message: string) => {
      const id = _toastSeq++;
      setToasts((prev) => [...prev, { id, tone, message }]);
      window.setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 4500);
    },
    [],
  );

  const reloadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [s, r] = await Promise.all([fetchSummary(), getTestRecipient()]);
      setSummary(s);
      setRecipient(r);
    } catch (err) {
      const e = err as AdminAlimtalkApiError;
      pushToast("error", e?.message ?? "데이터를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, [pushToast]);

  useEffect(() => {
    void reloadAll();
  }, [reloadAll]);

  async function refreshSummary() {
    try {
      const s = await fetchSummary();
      setSummary(s);
    } catch (err) {
      const e = err as AdminAlimtalkApiError;
      pushToast("error", e?.message ?? "요약 새로고침 실패");
    }
  }

  function onSendComplete() {
    // 발송 후 요약 재로드 — 카운트 즉시 반영. 429 가 발생했다면 quotaReached.
    void refreshSummary();
  }

  // 토스트에서 ALIMTALK_TEST_SEND_QUOTA_EXCEEDED 가 잡히면 quotaReached 표식.
  // TemplateRow 의 onToast 콜백 단순화를 위해 본 페이지에서는 메시지 매칭으로 처리.
  const handleToastFromChildren = useCallback(
    (tone: "success" | "error" | "warn", message: string) => {
      pushToast(tone, message);
      if (message.includes("하루 테스트 발송 한도")) {
        setQuotaReached(true);
      }
    },
    [pushToast],
  );

  const failureRate =
    summary && summary.totals.month_sent + summary.totals.month_failed > 0
      ? (
          (summary.totals.month_failed /
            (summary.totals.month_sent + summary.totals.month_failed)) *
          100
        ).toFixed(1)
      : "0.0";

  return (
    <main className={styles.page} aria-labelledby="alimtalkPageTitle">
      <header>
        <h1 id="alimtalkPageTitle" className={styles.pageTitle}>
          알림톡 관리
        </h1>
        <p className={styles.pageSubtitle}>
          템플릿별 발송 통계를 확인하고, 등록한 테스트 수신 번호로 임의 템플릿을 즉시
          시험 발송합니다.
        </p>
      </header>

      <TestRecipientCard
        recipient={recipient}
        canEdit={canEditRecipient}
        onChange={setRecipient}
        onToast={handleToastFromChildren}
      />

      <section className={styles.summaryGrid} aria-label="발송 요약">
        <div className={styles.summaryCard}>
          <span className={styles.summaryLabel}>오늘 발송 (성공/실패)</span>
          <span className={styles.summaryValue}>
            {summary?.totals.today_sent ?? 0}
            <span className={styles.summarySuffix}>/</span>
            <span
              className={
                (summary?.totals.today_failed ?? 0) > 0 ? styles.summaryFailed : ""
              }
            >
              {summary?.totals.today_failed ?? 0}
            </span>
          </span>
        </div>
        <div className={styles.summaryCard}>
          <span className={styles.summaryLabel}>이번 달 발송 (성공/실패)</span>
          <span className={styles.summaryValue}>
            {summary?.totals.month_sent ?? 0}
            <span className={styles.summarySuffix}>/</span>
            <span
              className={
                (summary?.totals.month_failed ?? 0) > 0 ? styles.summaryFailed : ""
              }
            >
              {summary?.totals.month_failed ?? 0}
            </span>
          </span>
        </div>
        <div className={styles.summaryCard}>
          <span className={styles.summaryLabel}>이번 달 실패율</span>
          <span className={styles.summaryValue}>{failureRate}%</span>
        </div>
      </section>

      <section className={styles.tableWrap} aria-label="템플릿 카탈로그">
        <table className={styles.table}>
          <thead>
            <tr>
              <th>채널</th>
              <th>카테고리</th>
              <th>템플릿 코드</th>
              <th>제목</th>
              <th>오늘 (성공/실패)</th>
              <th>이번 달 (성공/실패)</th>
              <th>액션</th>
            </tr>
          </thead>
          <tbody>
            {loading && !summary ? (
              <tr>
                <td colSpan={7} className={styles.emptyState}>
                  불러오는 중…
                </td>
              </tr>
            ) : !summary || summary.templates.length === 0 ? (
              <tr>
                <td colSpan={7} className={styles.emptyState}>
                  템플릿이 없습니다.
                </td>
              </tr>
            ) : (
              summary.templates.map((t) => (
                <TemplateRow
                  key={t.template_code}
                  template={t}
                  isRecipientSet={recipient?.is_set ?? false}
                  canTestSend={canTestSend}
                  quotaReached={quotaReached}
                  onSendComplete={onSendComplete}
                  onToast={handleToastFromChildren}
                />
              ))
            )}
          </tbody>
        </table>
      </section>

      {toasts.length > 0 && (
        <div className={styles.toastRegion} role="status" aria-live="polite">
          {toasts.map((t) => (
            <div key={t.id} className={styles.toast} data-tone={t.tone}>
              {t.message}
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
