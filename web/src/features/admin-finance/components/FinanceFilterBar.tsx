"use client";

import { useId } from "react";
import type { PaymentStatus } from "@/features/admin-finance/api/payments";
import styles from "./FinanceFilterBar.module.css";

const STATUS_OPTIONS: Array<{ value: PaymentStatus; label: string }> = [
  { value: "pending", label: "결제 대기" },
  { value: "success", label: "결제 완료" },
  { value: "failed", label: "결제 실패" },
  { value: "refunded", label: "환불 완료" },
  { value: "refund_pending", label: "환불 진행 중" },
];

const SEED_ERROR_CODES = [
  "INVALID_CARD_NUMBER",
  "EXPIRED_CARD",
  "INSUFFICIENT_BALANCE",
  "EXCEED_DAILY_LIMIT",
  "PAY_PROCESS_CANCELED",
  "INVALID_API_KEY",
];

export interface FinanceFilterValues {
  from: string;
  to: string;
  statusIn: PaymentStatus[];
  errorCode: string;
  /** 내부 user_id(숫자) 또는 사용자 계정 ID(이메일). 빈 문자열/undefined면 필터 미적용. */
  userId: string | undefined;
}

interface FilterBarProps extends FinanceFilterValues {
  onChange: (next: FinanceFilterValues) => void;
  /** 현재 페이지 응답에서 추출한 distinct error_code 목록 — 자동완성 보조 */
  errorCodeOptions?: string[];
}

export function FinanceFilterBar({
  from,
  to,
  statusIn,
  errorCode,
  userId,
  onChange,
  errorCodeOptions = [],
}: FilterBarProps) {
  const fromId = useId();
  const toId = useId();
  const errorCodeId = useId();
  const userIdInputId = useId();
  const datalistId = useId();

  const codeOptions = Array.from(
    new Set([...errorCodeOptions, ...SEED_ERROR_CODES]),
  );

  const toggleStatus = (s: PaymentStatus) => {
    const next = statusIn.includes(s)
      ? statusIn.filter((x) => x !== s)
      : [...statusIn, s];
    onChange({ from, to, statusIn: next, errorCode, userId });
  };

  const update = (patch: Partial<FinanceFilterValues>) => {
    onChange({ from, to, statusIn, errorCode, userId, ...patch });
  };

  return (
    <section className={styles.bar} role="toolbar" aria-label="결제 이벤트 필터">
      <div className={styles.row}>
        <label htmlFor={fromId} className={styles.label}>
          시작일
        </label>
        <input
          id={fromId}
          type="date"
          value={from}
          onChange={(e) => update({ from: e.target.value })}
          className={styles.input}
        />
        <label htmlFor={toId} className={styles.label}>
          종료일
        </label>
        <input
          id={toId}
          type="date"
          value={to}
          onChange={(e) => update({ to: e.target.value })}
          className={styles.input}
        />
      </div>

      <fieldset className={styles.statusGroup}>
        <legend className={styles.legend}>결제 상태</legend>
        {STATUS_OPTIONS.map((opt) => (
          <label key={opt.value} className={styles.statusLabel}>
            <input
              type="checkbox"
              checked={statusIn.includes(opt.value)}
              onChange={() => toggleStatus(opt.value)}
            />
            <span>{opt.label}</span>
          </label>
        ))}
      </fieldset>

      <div className={styles.row}>
        <label htmlFor={errorCodeId} className={styles.label}>
          PG 에러 코드
        </label>
        <input
          id={errorCodeId}
          type="text"
          value={errorCode}
          onChange={(e) => update({ errorCode: e.target.value })}
          list={datalistId}
          maxLength={50}
          className={styles.input}
          placeholder="예: INVALID_CARD_NUMBER"
        />
        <datalist id={datalistId}>
          {codeOptions.map((c) => (
            <option key={c} value={c} />
          ))}
        </datalist>

        <label htmlFor={userIdInputId} className={styles.label}>
          사용자 ID
        </label>
        <input
          id={userIdInputId}
          type="text"
          inputMode="email"
          autoComplete="off"
          value={userId ?? ""}
          onChange={(e) => {
            const v = e.target.value;
            update({ userId: v.trim() ? v : undefined });
          }}
          className={styles.input}
          placeholder="계정 ID(이메일) 또는 내부 번호"
        />
      </div>
    </section>
  );
}
