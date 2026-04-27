"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import styles from "./SMSCodeInput.module.css";

interface SMSCodeInputProps {
  length?: number;
  onComplete: (code: string) => void;
  onResend: () => Promise<void>;
  cooldownSeconds?: number;
  error?: string;
  disabled?: boolean;
}

/**
 * SMS 6자리 OTP 입력 — 개별 칸, 자동 커서 이동, Paste 지원, 쿨다운 타이머 (UX-DR7).
 * iOS: autocomplete="one-time-code"
 */
export function SMSCodeInput({
  length = 6,
  onComplete,
  onResend,
  cooldownSeconds = 60,
  error,
  disabled = false,
}: SMSCodeInputProps) {
  const [digits, setDigits] = useState<string[]>(Array(length).fill(""));
  const [cooldown, setCooldown] = useState(cooldownSeconds);
  const [resending, setResending] = useState(false);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 쿨다운 시작
  const startCooldown = useCallback(() => {
    setCooldown(cooldownSeconds);
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setCooldown((prev) => {
        if (prev <= 1) {
          clearInterval(timerRef.current!);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }, [cooldownSeconds]);

  useEffect(() => {
    startCooldown();
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [startCooldown]);

  // 완성 감지
  useEffect(() => {
    const full = digits.join("");
    if (full.length === length && digits.every((d) => /^\d$/.test(d))) {
      onComplete(full);
    }
  }, [digits, length, onComplete]);

  const updateDigit = (index: number, val: string) => {
    const next = [...digits];
    next[index] = val.slice(-1);
    setDigits(next);
    if (val && index < length - 1) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !digits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
    if (e.key === "ArrowLeft" && index > 0) inputRefs.current[index - 1]?.focus();
    if (e.key === "ArrowRight" && index < length - 1) inputRefs.current[index + 1]?.focus();
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, length);
    const next = Array(length).fill("");
    pasted.split("").forEach((ch, i) => { next[i] = ch; });
    setDigits(next);
    const focusIdx = Math.min(pasted.length, length - 1);
    inputRefs.current[focusIdx]?.focus();
  };

  const handleResend = async () => {
    if (cooldown > 0 || resending) return;
    setResending(true);
    try {
      await onResend();
      setDigits(Array(length).fill(""));
      inputRefs.current[0]?.focus();
      startCooldown();
    } finally {
      setResending(false);
    }
  };

  const cellClass = error ? `${styles.cell} ${styles.cellError}` : styles.cell;

  return (
    <div>
      <div className={styles.cellRow}>
        {digits.map((d, i) => (
          <input
            key={i}
            ref={(el) => { inputRefs.current[i] = el; }}
            type="text"
            inputMode="numeric"
            maxLength={1}
            autoComplete={i === 0 ? "one-time-code" : "off"}
            value={d}
            disabled={disabled}
            aria-label={`인증번호 ${i + 1}번째 자리`}
            onChange={(e) => updateDigit(i, e.target.value.replace(/\D/g, ""))}
            onKeyDown={(e) => handleKeyDown(i, e)}
            onPaste={i === 0 ? handlePaste : undefined}
            onFocus={(e) => e.target.select()}
            className={cellClass}
          />
        ))}
      </div>

      {error && (
        <p role="alert" className={styles.errorText}>
          {error}
        </p>
      )}

      <div className={styles.cooldownRow}>
        {cooldown > 0 ? (
          <span>재전송 ({cooldown}초 후)</span>
        ) : (
          <button
            type="button"
            onClick={handleResend}
            disabled={resending}
            className={
              resending
                ? `${styles.resendBtn} ${styles.resendBtnDisabled}`
                : styles.resendBtn
            }
          >
            {resending ? "전송 중..." : "인증번호 재전송"}
          </button>
        )}
      </div>
    </div>
  );
}
