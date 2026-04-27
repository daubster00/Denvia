"use client";

import { useRef } from "react";
import styles from "@/styles/auth-forms.module.css";

interface PhoneNumberFieldProps {
  value: string;
  onChange: (value: string) => void;
  error?: string;
  id?: string;
  autoFocus?: boolean;
}

function formatPhone(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 11);
  if (digits.length <= 3) return digits;
  if (digits.length <= 7) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  return `${digits.slice(0, 3)}-${digits.slice(3, 7)}-${digits.slice(7)}`;
}

/** 포맷된 문자열에서 숫자 n개 이후의 커서 위치를 반환한다. */
function cursorAfterFormat(formatted: string, digitsBeforeCursor: number): number {
  let seen = 0;
  for (let i = 0; i < formatted.length; i++) {
    if (seen === digitsBeforeCursor) return i;
    if (/\d/.test(formatted[i])) seen++;
  }
  return formatted.length;
}

/**
 * 휴대폰 번호 입력 필드 — 010-XXXX-XXXX 자동 포맷팅 (UX-DR18).
 */
export function PhoneNumberField({ value, onChange, error, id = "phone", autoFocus }: PhoneNumberFieldProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const nextCursor = useRef<number | null>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    const cursorPos = e.target.selectionStart ?? raw.length;
    const digitsBeforeCursor = raw.slice(0, cursorPos).replace(/\D/g, "").length;

    const formatted = formatPhone(raw);
    nextCursor.current = cursorAfterFormat(formatted, digitsBeforeCursor);
    onChange(formatted);

    // React가 DOM을 업데이트한 직후 커서를 복원한다
    requestAnimationFrame(() => {
      if (inputRef.current && nextCursor.current !== null) {
        inputRef.current.setSelectionRange(nextCursor.current, nextCursor.current);
        nextCursor.current = null;
      }
    });
  };

  return (
    <div>
      <label htmlFor={id} className={styles.fieldLabel}>
        휴대폰 번호 <span aria-label="필수" className={styles.required}>*</span>
      </label>
      <input
        ref={inputRef}
        id={id}
        type="tel"
        inputMode="numeric"
        autoComplete="tel"
        placeholder="010-0000-0000"
        value={value}
        onChange={handleChange}
        autoFocus={autoFocus}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-error` : undefined}
        className={error ? `${styles.input} ${styles.inputError}` : styles.input}
      />
      {error && (
        <p id={`${id}-error`} role="alert" className={styles.fieldError}>
          {error}
        </p>
      )}
    </div>
  );
}
