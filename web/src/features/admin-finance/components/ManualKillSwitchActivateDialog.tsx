"use client";

/**
 * Story 9.2 — 수동 비상 정지 발동 2단계 확인 다이얼로그.
 *
 * UX-DR27 의도적 마찰:
 * - X 닫기 버튼 없음 / ESC 키 차단 / 배경 클릭 닫기 차단
 * - 사유 textarea 4~500자 zod 검증
 * - "이해했습니다" 체크박스 + 사유 입력 후 Danger 버튼 활성
 *
 * Story 1.7 ConfirmWithdrawPopup 패턴 차용.
 */

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { useAlertStore } from "@/stores/alert-store";
import { useToastStore } from "@/stores/toast-store";

import {
  KillswitchApiError,
  activateManualKillswitch,
} from "../api/killswitch";
import { KILLSWITCH_STATUS_QUERY_KEY } from "../hooks/useKillswitchStatus";
import styles from "./ManualKillSwitchActivateDialog.module.css";

interface ManualKillSwitchActivateDialogProps {
  open: boolean;
  onClose: () => void;
}

const reasonSchema = z
  .string()
  .min(4, "사유는 4자 이상 입력해주세요.")
  .max(500, "사유는 500자 이내로 입력해주세요.");

export function ManualKillSwitchActivateDialog({
  open,
  onClose,
}: ManualKillSwitchActivateDialogProps) {
  const qc = useQueryClient();
  const showAlert = useAlertStore((s) => s.show);
  const showToast = useToastStore((s) => s.show);

  const [reason, setReason] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 다이얼로그 열림 시 상태 초기화 + textarea focus.
  useEffect(() => {
    if (open) {
      setReason("");
      setAcknowledged(false);
      setReasonError(null);
      setSubmitting(false);
      window.setTimeout(() => textareaRef.current?.focus(), 50);
    }
  }, [open]);

  // ESC 차단 — UX-DR27 의도적 마찰.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
      }
    };
    document.addEventListener("keydown", onKey, { capture: true });
    return () => document.removeEventListener("keydown", onKey, { capture: true } as any);
  }, [open]);

  if (!open) return null;

  const reasonValid = reasonSchema.safeParse(reason).success;
  const canSubmit = reasonValid && acknowledged && !submitting;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    const parsed = reasonSchema.safeParse(reason);
    if (!parsed.success) {
      setReasonError(parsed.error.issues[0]?.message ?? "사유가 올바르지 않습니다.");
      return;
    }
    setSubmitting(true);
    setReasonError(null);
    try {
      await activateManualKillswitch(parsed.data);
      qc.invalidateQueries({ queryKey: KILLSWITCH_STATUS_QUERY_KEY });
      showToast("수동 비상 정지가 활성화되었습니다", 3000);
      onClose();
    } catch (err) {
      const apiErr = err instanceof KillswitchApiError ? err : null;
      const code = apiErr?.code ?? "UNKNOWN_ERROR";
      if (code === "KILLSWITCH_ALREADY_ACTIVE") {
        showAlert({
          level: "warning",
          title: "이미 활성화됨",
          description:
            "다른 관리자가 이미 수동 비상 정지를 활성화했습니다. 화면을 새로고침합니다.",
        });
        qc.invalidateQueries({ queryKey: KILLSWITCH_STATUS_QUERY_KEY });
        onClose();
      } else {
        showAlert({
          level: "error",
          title: "비상 정지 발동 실패",
          description: apiErr?.message ?? "잠시 후 다시 시도해주세요.",
        });
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.dimmer} role="presentation">
      <div
        ref={dialogRef}
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="killswitch-activate-heading"
      >
        <h2 id="killswitch-activate-heading" className={styles.heading}>
          ⚠ 전체 정지 발동 확인
        </h2>

        <p className={styles.description}>
          이 작업은{" "}
          <span className={styles.descriptionStrong}>
            모든 사용자(무료·유료 모두)
          </span>
          의 신규 질의를 즉시 차단합니다. 이용약관 §N(비상 정지 시 자동 연장 조항)이
          적용되어, 발동 시점부터 해제 시점까지의 기간만큼 모든 활성 유료 구독자의
          만료일이 자동으로 연장됩니다.
        </p>

        <div className={styles.fieldGroup}>
          <label htmlFor="killswitch-reason" className={styles.fieldLabel}>
            발동 사유 (4~500자, 필수)
          </label>
          <textarea
            id="killswitch-reason"
            ref={textareaRef}
            className={
              reasonError
                ? `${styles.textarea} ${styles.textareaError}`
                : styles.textarea
            }
            value={reason}
            maxLength={500}
            onChange={(e) => {
              setReason(e.target.value);
              if (reasonError) setReasonError(null);
            }}
            aria-invalid={!!reasonError}
            aria-describedby="killswitch-reason-hint"
            placeholder="예: OpenAI 장애 대응 — 11/24 14:00 KST 응답 지연 100% 발생"
          />
          <p id="killswitch-reason-hint" className={styles.fieldHint}>
            {reason.length}/500자 — 감사 로그(audit_logs)에 본문 그대로 기록됩니다.
          </p>
          {reasonError && (
            <p role="alert" className={styles.fieldError}>
              {reasonError}
            </p>
          )}
        </div>

        <label className={styles.acknowledgeRow}>
          <input
            type="checkbox"
            className={styles.acknowledgeCheckbox}
            checked={acknowledged}
            onChange={(e) => setAcknowledged(e.target.checked)}
          />
          <span className={styles.acknowledgeText}>
            이해했습니다. 모든 사용자 질의가 즉시 차단되고, 활성 유료 구독자의 만료일이
            정지 기간만큼 자동 연장됩니다.
          </span>
        </label>

        <div className={styles.actionRow}>
          <button
            type="button"
            className={styles.cancelBtn}
            onClick={onClose}
            disabled={submitting}
          >
            취소
          </button>
          <button
            type="button"
            className={styles.dangerBtn}
            onClick={handleSubmit}
            disabled={!canSubmit}
          >
            {submitting ? "처리 중..." : "전체 정지 발동"}
          </button>
        </div>
      </div>
    </div>
  );
}
