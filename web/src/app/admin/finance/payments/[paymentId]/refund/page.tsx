"use client";

/**
 * 관리자 운영 환불 입력 화면 — Story 9.1 v1.1 (ADR-0001 편차 #5).
 *
 * 흐름:
 * 1) GET refund-quote → 잔액·전액·일할·청약철회·다음 sequence 묶음.
 * 2) 관리자가 cancel_amount(원) + reason_category + memo 입력.
 *    - cancel_amount 가드: 0 초과 AND refundable_balance 이하.
 *    - 전액/일할 권장값은 클릭 한 번에 입력 칸에 채워주는 버튼으로 표기.
 *    - is_within_cooling_off=true면 별도 배지로 청약철회 대안 안내.
 * 3) "환불 처리" 클릭 → ConfirmDialog 2단계 확인 (UX-DR27).
 * 4) POST /refunds → 성공 시 quote 무효화 + 환불 이력 갱신 + 안내 메시지.
 *
 * 코드 정책:
 * - 인라인 CSS 금지 — 본 모듈의 `page.module.css`에서 모든 스타일을 관리.
 * - 좌측 정렬 — `.page { max-width: 1300px; margin-left: 0; }`.
 * - 모든 금액·날짜 표기는 KST + 한국어 로케일.
 */

import { useMemo, useState, use } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ConfirmDialog } from "@/components/layout/ConfirmDialog";
import {
  createRefund,
  fetchRefundList,
  fetchRefundQuote,
  REFUND_REASON_LABELS,
  RefundApiError,
  type RefundCreateResponse,
  type RefundListResponse,
  type RefundQuoteResponse,
  type RefundReasonCategory,
} from "@/features/admin-finance/api/refunds";
import styles from "./page.module.css";

interface PageProps {
  params: Promise<{ paymentId: string }>;
}

function parsePaymentId(raw: string): number | null {
  if (!/^\d+$/.test(raw)) return null;
  const n = Number(raw);
  return Number.isInteger(n) && n >= 1 ? n : null;
}

function fmtKrw(n: number): string {
  return `${n.toLocaleString("ko-KR")}원`;
}

function fmtKstFull(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("ko-KR", { timeZone: "Asia/Seoul", hour12: false });
}

function fmtKstDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("ko-KR", { timeZone: "Asia/Seoul" });
}

const REASON_OPTIONS: ReadonlyArray<RefundReasonCategory> = [
  "customer_complaint",
  "duplicate_payment",
  "system_error",
  "special_mid_cancel",
  "other",
];

const ERROR_MESSAGES: Record<string, string> = {
  PAYMENT_NOT_REFUNDABLE: "이 결제는 환불 가능한 상태가 아닙니다. (status가 success가 아님)",
  NO_REFUNDABLE_BALANCE: "이 결제는 이미 전액 환불되어 추가 환불할 수 없습니다.",
  CANCEL_AMOUNT_EXCEEDS_BALANCE: "환불 금액이 잔액을 초과합니다.",
  PG_REFUND_UNAVAILABLE: "PG와의 통신이 일시적으로 실패했습니다. 잠시 후 다시 시도해주세요.",
  PG_REFUND_FAILED: "PG가 환불을 거부했습니다. PG 에러 메시지를 확인해주세요.",
  REFUND_RACE_DETECTED:
    "동시 환불 요청이 감지되었습니다. PG에 이미 처리되었을 수 있으니 환불 이력을 다시 확인해주세요.",
  PAYMENT_NOT_FOUND: "해당 결제를 찾을 수 없습니다.",
};

export default function AdminPaymentRefundPage({ params }: PageProps) {
  const { paymentId: rawId } = use(params);
  const paymentId = parsePaymentId(rawId);

  if (paymentId === null) {
    return (
      <section className={styles.page}>
        <div className={styles.breadcrumb}>
          <Link href="/admin/finance/payments" className={styles.backLink}>
            ← 결제 기록
          </Link>
        </div>
        <div className={styles.invalidBox} role="alert">
          잘못된 결제 ID입니다.
        </div>
      </section>
    );
  }

  return <RefundView paymentId={paymentId} />;
}

interface ViewProps {
  paymentId: number;
}

function RefundView({ paymentId }: ViewProps) {
  const qc = useQueryClient();

  const quote = useQuery<RefundQuoteResponse>({
    queryKey: ["admin", "finance", "refund-quote", paymentId] as const,
    queryFn: () => fetchRefundQuote(paymentId),
    staleTime: 5_000,
    refetchOnWindowFocus: false,
  });

  const history = useQuery<RefundListResponse>({
    queryKey: ["admin", "finance", "refund-history", paymentId] as const,
    queryFn: () => fetchRefundList(paymentId),
    staleTime: 5_000,
    refetchOnWindowFocus: false,
  });

  const [cancelAmountText, setCancelAmountText] = useState<string>("");
  const [reason, setReason] = useState<RefundReasonCategory>("customer_complaint");
  const [memo, setMemo] = useState<string>("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [successInfo, setSuccessInfo] = useState<RefundCreateResponse | null>(
    null,
  );

  const mutation = useMutation<RefundCreateResponse, RefundApiError>({
    mutationFn: async () => {
      const cancelAmount = Number(cancelAmountText);
      return createRefund(paymentId, {
        cancel_amount: cancelAmount,
        reason_category: reason,
        memo: memo.trim() === "" ? null : memo,
      });
    },
    onSuccess: (res) => {
      setSuccessInfo(res);
      setConfirmOpen(false);
      setCancelAmountText("");
      setMemo("");
      void qc.invalidateQueries({
        queryKey: ["admin", "finance", "refund-quote", paymentId],
      });
      void qc.invalidateQueries({
        queryKey: ["admin", "finance", "refund-history", paymentId],
      });
      void qc.invalidateQueries({
        queryKey: ["admin", "finance", "payment-events"],
      });
    },
  });

  const parsedAmount = useMemo(() => {
    if (cancelAmountText === "") return null;
    if (!/^\d+$/.test(cancelAmountText)) return null;
    const n = Number(cancelAmountText);
    return Number.isInteger(n) && n > 0 ? n : null;
  }, [cancelAmountText]);

  const refundable = quote.data?.refundable_balance ?? 0;
  const isAmountValid =
    parsedAmount !== null && parsedAmount > 0 && parsedAmount <= refundable;
  const noBalance = quote.isSuccess && refundable <= 0;

  const inferredKind: "full" | "partial" | null = useMemo(() => {
    if (parsedAmount === null) return null;
    if (parsedAmount === refundable) return "full";
    return "partial";
  }, [parsedAmount, refundable]);

  const submitDisabled =
    !quote.isSuccess ||
    noBalance ||
    !isAmountValid ||
    mutation.isPending;

  const apiErrorMessage = (() => {
    if (!mutation.error) return undefined;
    const err = mutation.error;
    if (err instanceof RefundApiError) {
      const known = ERROR_MESSAGES[err.code];
      if (known) {
        if (err.code === "CANCEL_AMOUNT_EXCEEDS_BALANCE") {
          const balance = err.details?.refundable_balance as number | undefined;
          if (typeof balance === "number") {
            return `${known} (잔액 ${fmtKrw(balance)})`;
          }
        }
        if (err.code === "PG_REFUND_FAILED") {
          const pgMsg = err.details?.pg_error_message;
          if (typeof pgMsg === "string" && pgMsg.length > 0) {
            return `${known} — PG 메시지: ${pgMsg}`;
          }
        }
        return known;
      }
      return err.message;
    }
    return "예상치 못한 오류가 발생했습니다.";
  })();

  return (
    <section className={styles.page} aria-labelledby="refund-page-title">
      <div className={styles.breadcrumb}>
        <Link href="/admin/finance/payments" className={styles.backLink}>
          ← 결제 기록
        </Link>
      </div>

      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <h1 id="refund-page-title" className={styles.title}>
            환불 처리 — 결제 #{paymentId}
          </h1>
          <p className={styles.caption}>
            관리자가 환불 금액과 사유를 직접 입력해 부분/전액 환불을 처리합니다.
            잔액 가드·청약철회 표기는 자동입니다.
          </p>
        </div>
      </header>

      {quote.isLoading && (
        <div className={styles.statusBox}>환불 정보를 불러오는 중…</div>
      )}

      {quote.error && (
        <div className={styles.errorBox} role="alert">
          <p>환불 정보를 불러오지 못했습니다.</p>
          {quote.error instanceof RefundApiError && (
            <p className={styles.subMsg}>
              {ERROR_MESSAGES[quote.error.code] ?? quote.error.message}
            </p>
          )}
          <button
            type="button"
            className={styles.ghostBtn}
            onClick={() => quote.refetch()}
          >
            다시 시도
          </button>
        </div>
      )}

      {quote.data && (
        <>
          <section
            className={styles.quoteCard}
            aria-label="환불 참고 계산값"
          >
            <div className={styles.quoteGrid}>
              <Field label="결제 원금" value={fmtKrw(quote.data.payment_amount)} />
              <Field
                label="누적 환불"
                value={`${fmtKrw(quote.data.refunded_total)} (${quote.data.existing_refunds_count}회)`}
              />
              <Field
                label="환불 가능 잔액"
                value={fmtKrw(quote.data.refundable_balance)}
                emphasis
              />
              <Field
                label="결제 후 경과"
                value={`${quote.data.cooling_off_days_since_charge}일`}
              />
              <Field
                label="구독 기간 동안 질문"
                value={`${quote.data.cooling_off_qa_count}건`}
              />
              <Field
                label="다음 환불 회차"
                value={`${quote.data.next_refund_sequence}회차`}
              />
              <Field
                label="구독 기간 시작"
                value={fmtKstFull(quote.data.subscription_period_start)}
              />
              <Field
                label="구독 기간 종료"
                value={fmtKstFull(quote.data.subscription_period_end)}
              />
            </div>

            {quote.data.is_within_cooling_off && (
              <div className={styles.coolingOffBadge} role="status">
                <strong>청약철회 가능</strong>
                <span>
                  결제 후 7일 이내 AND 질문 0건 — 사용자에게 셀프 청약철회를 안내하면
                  전액 환불 + 즉시 해지가 자동 처리됩니다. 본 화면을 통한 운영 환불은
                  사용자 셀프 처리가 곤란한 경우에만 사용해주세요.
                </span>
              </div>
            )}

            {noBalance && (
              <div className={styles.noBalanceBox} role="alert">
                잔액이 0원입니다. 추가 환불은 불가합니다.
              </div>
            )}
          </section>

          {!noBalance && (
            <section
              className={styles.formCard}
              aria-label="환불 입력"
            >
              <div className={styles.fieldRow}>
                <label htmlFor="cancel-amount" className={styles.fieldLabel}>
                  환불 금액(원) <span className={styles.required}>*</span>
                </label>
                <div className={styles.amountInputWrap}>
                  <input
                    id="cancel-amount"
                    type="text"
                    inputMode="numeric"
                    autoComplete="off"
                    className={styles.amountInput}
                    value={cancelAmountText}
                    placeholder="예: 19800"
                    onChange={(e) =>
                      setCancelAmountText(e.target.value.replace(/[^\d]/g, ""))
                    }
                    aria-invalid={
                      cancelAmountText !== "" && !isAmountValid ? "true" : "false"
                    }
                    aria-describedby="cancel-amount-help"
                  />
                  <button
                    type="button"
                    className={styles.suggestBtn}
                    onClick={() =>
                      setCancelAmountText(String(quote.data.full_refund_amount))
                    }
                    disabled={quote.data.full_refund_amount <= 0}
                  >
                    전액 {fmtKrw(quote.data.full_refund_amount)}
                  </button>
                  <button
                    type="button"
                    className={styles.suggestBtn}
                    onClick={() =>
                      setCancelAmountText(String(quote.data.prorated_amount))
                    }
                    disabled={quote.data.prorated_amount <= 0}
                    title={`일할 권장: 남은 ${quote.data.prorated_days_remaining}일 / 총 ${quote.data.prorated_total_days}일`}
                  >
                    일할 {fmtKrw(quote.data.prorated_amount)}
                  </button>
                </div>
                <p id="cancel-amount-help" className={styles.helpText}>
                  0 초과, 잔액 {fmtKrw(refundable)} 이하의 정수(원). 일할 권장값은
                  KST 캘린더 기준 (남은 {quote.data.prorated_days_remaining}일 / 총{" "}
                  {quote.data.prorated_total_days}일).
                </p>
                {cancelAmountText !== "" && !isAmountValid && (
                  <p className={styles.fieldError} role="alert">
                    {parsedAmount === null
                      ? "정수(원)만 입력해주세요."
                      : parsedAmount > refundable
                        ? `잔액 ${fmtKrw(refundable)}을 초과할 수 없습니다.`
                        : "0보다 큰 금액을 입력해주세요."}
                  </p>
                )}
              </div>

              <div className={styles.fieldRow}>
                <label htmlFor="refund-reason" className={styles.fieldLabel}>
                  환불 사유 <span className={styles.required}>*</span>
                </label>
                <select
                  id="refund-reason"
                  className={styles.select}
                  value={reason}
                  onChange={(e) =>
                    setReason(e.target.value as RefundReasonCategory)
                  }
                >
                  {REASON_OPTIONS.map((r) => (
                    <option key={r} value={r}>
                      {REFUND_REASON_LABELS[r]}
                    </option>
                  ))}
                </select>
              </div>

              <div className={styles.fieldRow}>
                <label htmlFor="refund-memo" className={styles.fieldLabel}>
                  메모 (선택, 최대 500자)
                </label>
                <textarea
                  id="refund-memo"
                  className={styles.textarea}
                  value={memo}
                  rows={4}
                  maxLength={500}
                  onChange={(e) => setMemo(e.target.value)}
                  placeholder="환불 사유에 대한 추가 메모. PG cancelReason으로는 앞 200자만 전달됩니다."
                />
                <p className={styles.helpText}>
                  {memo.length} / 500자
                </p>
              </div>

              {inferredKind && (
                <div className={styles.kindHint}>
                  이 환불은{" "}
                  <strong>
                    {inferredKind === "full"
                      ? quote.data.next_refund_sequence === 1
                        ? "단발 전액 환불"
                        : "잔액 전액 환불(누적)"
                      : "부분 환불"}
                  </strong>{" "}
                  로 기록됩니다.
                  {inferredKind === "full" && (
                    <> 처리 후 결제는 환불 완료 상태로, 구독은 즉시 해지됩니다.</>
                  )}
                </div>
              )}

              {apiErrorMessage && (
                <p className={styles.formError} role="alert">
                  {apiErrorMessage}
                </p>
              )}

              <div className={styles.actions}>
                <button
                  type="button"
                  className={styles.submitBtn}
                  disabled={submitDisabled}
                  onClick={() => setConfirmOpen(true)}
                >
                  환불 처리
                </button>
              </div>
            </section>
          )}
        </>
      )}

      <section className={styles.historyCard} aria-label="환불 이력">
        <h2 className={styles.sectionTitle}>환불 이력</h2>
        {history.isLoading && (
          <div className={styles.statusBox}>환불 이력을 불러오는 중…</div>
        )}
        {history.error && (
          <div className={styles.errorBox} role="alert">
            환불 이력을 불러오지 못했습니다.
          </div>
        )}
        {history.data && history.data.total === 0 && (
          <p className={styles.emptyMsg}>이 결제의 환불 이력이 없습니다.</p>
        )}
        {history.data && history.data.total > 0 && (
          <table className={styles.historyTable}>
            <thead>
              <tr>
                <th>회차</th>
                <th>처리일(KST)</th>
                <th>금액</th>
                <th>사유</th>
                <th>처리 관리자</th>
                <th>메모</th>
              </tr>
            </thead>
            <tbody>
              {history.data.items.map((r) => (
                <tr key={r.id}>
                  <td>{r.refund_sequence}회</td>
                  <td>{fmtKstDate(r.created_at)}</td>
                  <td className={styles.amountCell}>{fmtKrw(r.cancel_amount)}</td>
                  <td>{REFUND_REASON_LABELS[r.reason_category]}</td>
                  <td>{r.admin_email_masked}</td>
                  <td className={styles.memoCell}>{r.memo ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {successInfo && (
        <div className={styles.successBanner} role="status">
          환불이 처리되었습니다. (id: {successInfo.refund_id} ·{" "}
          {successInfo.refund_sequence}회차 · {fmtKrw(successInfo.cancel_amount)})
        </div>
      )}

      <ConfirmDialog
        open={confirmOpen}
        title="환불을 처리하시겠습니까?"
        description={
          parsedAmount === null
            ? undefined
            : `환불 금액 ${fmtKrw(parsedAmount)} · 사유: ${REFUND_REASON_LABELS[reason]}${
                inferredKind === "full"
                  ? " · 결제 환불 완료 + 구독 즉시 해지가 함께 처리됩니다."
                  : " · 결제는 success 유지, 구독은 변경 없음."
              }`
        }
        confirmLabel="환불 처리"
        cancelLabel="취소"
        danger
        isSubmitting={mutation.isPending}
        errorMessage={apiErrorMessage}
        onConfirm={() => mutation.mutate()}
        onCancel={() => setConfirmOpen(false)}
      />
    </section>
  );
}

interface FieldProps {
  label: string;
  value: string;
  emphasis?: boolean;
}

function Field({ label, value, emphasis }: FieldProps) {
  return (
    <div className={styles.field}>
      <span className={styles.fieldKey}>{label}</span>
      <span
        className={emphasis ? `${styles.fieldVal} ${styles.fieldValStrong}` : styles.fieldVal}
      >
        {value}
      </span>
    </div>
  );
}
