"use client";

/**
 * 상단바 우측에 노출되는 OpenAI 워밍업 루프 토글.
 *
 * 가시성 규칙:
 * - 마스터는 항상 노출.
 * - 그 외 등급은 권한 매트릭스에서 "/admin/feature/openai-warmup" 이 켜져 있을 때만 노출.
 * 권한이 없는 관리자에게는 라벨조차 보이지 않도록 컴포넌트 자체를 렌더하지 않는다.
 */

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/types/api";
import {
  fetchWarmupStatus,
  startWarmup,
  stopWarmup,
  type WarmupStatus,
} from "@/features/admin-openai-warmup/api";
import styles from "./AdminWarmupToggle.module.css";

interface Props {
  canSee: boolean;
}

const QUERY_KEY = ["admin-openai-warmup-status"];

function formatRelative(iso: string | null): string {
  if (!iso) return "-";
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return "-";
  const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (diffSec < 60) return `${diffSec}초 전`;
  const m = Math.floor(diffSec / 60);
  if (m < 60) return `${m}분 전`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}시간 전`;
  return new Date(iso).toLocaleString();
}

export function AdminWarmupToggle({ canSee }: Props) {
  const queryClient = useQueryClient();
  const [now, setNow] = useState(() => Date.now());

  const { data, isLoading, isError, error } = useQuery<WarmupStatus, ApiError>({
    queryKey: QUERY_KEY,
    queryFn: fetchWarmupStatus,
    enabled: canSee,
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
  });

  const startMutation = useMutation<WarmupStatus, ApiError>({
    mutationFn: startWarmup,
    onSuccess: (next) => queryClient.setQueryData(QUERY_KEY, next),
  });

  const stopMutation = useMutation<WarmupStatus, ApiError>({
    mutationFn: stopWarmup,
    onSuccess: (next) => queryClient.setQueryData(QUERY_KEY, next),
  });

  // "마지막 핑 ~초 전" 라벨이 매초 자동으로 새로고침되도록 1초 틱.
  useEffect(() => {
    if (!canSee) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [canSee]);
  // now 변경에만 의존하는 라벨 — 미사용 변수 경고 회피용 참조.
  void now;

  const running = data?.running ?? false;
  const busy = startMutation.isPending || stopMutation.isPending;

  const lastPingLabel = useMemo(
    () => formatRelative(data?.last_ping_at ?? null),
    [data?.last_ping_at, now],
  );

  if (!canSee) {
    return null;
  }

  const handleClick = () => {
    if (busy) return;
    if (running) {
      stopMutation.mutate();
    } else {
      startMutation.mutate();
    }
  };

  const statusText = (() => {
    if (isLoading) return "확인 중";
    if (isError) {
      const code = error?.code;
      if (code === "OPENAI_KEY_MISSING") return "키 없음";
      if (code === "ADMIN_FORBIDDEN_PAGE" || code === "ADMIN_FORBIDDEN_GRADE")
        return "권한 없음";
      return "오류";
    }
    if (running) return "가동 중";
    return "정지";
  })();

  const mutationError =
    startMutation.error?.message ?? stopMutation.error?.message ?? null;

  return (
    <div className={styles.wrap} role="group" aria-label="AI 워밍업">
      <div className={styles.info}>
        <span className={styles.title}>AI 워밍업</span>
        <span
          className={
            running ? `${styles.badge} ${styles.badgeOn}` : styles.badge
          }
          aria-live="polite"
        >
          {statusText}
        </span>
        {data && (
          <span
            className={styles.meta}
            title={`주기 ${data.interval_seconds}초 · 모델 ${data.model} · 누적 ${data.total_pings}회`}
          >
            마지막: {lastPingLabel}
          </span>
        )}
      </div>
      <button
        type="button"
        onClick={handleClick}
        className={
          running
            ? `${styles.button} ${styles.buttonStop}`
            : `${styles.button} ${styles.buttonStart}`
        }
        disabled={busy || isLoading}
        aria-pressed={running}
      >
        {busy ? "처리 중..." : running ? "정지" : "시작"}
      </button>
      {mutationError && (
        <span className={styles.error} role="alert">
          {mutationError}
        </span>
      )}
    </div>
  );
}
