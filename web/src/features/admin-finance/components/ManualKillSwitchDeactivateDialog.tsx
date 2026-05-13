"use client";

/**
 * Story 9.2 — 수동 비상 정지 해제 1단계 확인 다이얼로그.
 * 정상 운영 복귀이므로 위험도 낮음 → X/ESC/배경 닫기 허용.
 */

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useAlertStore } from "@/stores/alert-store";
import { useToastStore } from "@/stores/toast-store";

import {
  KillswitchApiError,
  deactivateManualKillswitch,
} from "../api/killswitch";
import { KILLSWITCH_STATUS_QUERY_KEY } from "../hooks/useKillswitchStatus";
import styles from "./ManualKillSwitchDeactivateDialog.module.css";

interface ManualKillSwitchDeactivateDialogProps {
  open: boolean;
  onClose: () => void;
  durationActivatedAt: string | null;
}

function formatHours(activatedAtIso: string | null): string {
  if (!activatedAtIso) return "약 0";
  const start = new Date(activatedAtIso).getTime();
  if (Number.isNaN(start)) return "약 0";
  const diffMs = Date.now() - start;
  const hours = Math.max(1, Math.round(diffMs / (3600 * 1000)));
  return `약 ${hours}`;
}

export function ManualKillSwitchDeactivateDialog({
  open,
  onClose,
  durationActivatedAt,
}: ManualKillSwitchDeactivateDialogProps) {
  const qc = useQueryClient();
  const showAlert = useAlertStore((s) => s.show);
  const showToast = useToastStore((s) => s.show);
  const [submitting, setSubmitting] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const hours = formatHours(durationActivatedAt);

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await deactivateManualKillswitch();
      qc.invalidateQueries({ queryKey: KILLSWITCH_STATUS_QUERY_KEY });
      showToast("수동 비상 정지를 해제했습니다", 3000);
      onClose();
    } catch (err) {
      const apiErr = err instanceof KillswitchApiError ? err : null;
      const code = apiErr?.code ?? "UNKNOWN_ERROR";
      if (code === "KILLSWITCH_NOT_ACTIVE") {
        showAlert({
          level: "info",
          title: "이미 해제됨",
          description: "다른 관리자가 이미 해제했습니다. 화면을 새로고침합니다.",
        });
        qc.invalidateQueries({ queryKey: KILLSWITCH_STATUS_QUERY_KEY });
        onClose();
      } else {
        showAlert({
          level: "error",
          title: "비상 정지 해제 실패",
          description: apiErr?.message ?? "잠시 후 다시 시도해주세요.",
        });
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className={styles.dimmer}
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget && !submitting) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="killswitch-deactivate-heading"
      >
        <h2 id="killswitch-deactivate-heading" className={styles.heading}>
          전체 정지 해제
        </h2>
        <p className={styles.description}>
          전체 정지를 해제하고 서비스를 재개합니다. 유료 구독자의 만료일이 정지 기간(
          {hours}시간)만큼 자동 연장됩니다.
        </p>
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
            className={styles.primaryBtn}
            onClick={handleSubmit}
            disabled={submitting}
          >
            {submitting ? "처리 중..." : "해제"}
          </button>
        </div>
      </div>
    </div>
  );
}
