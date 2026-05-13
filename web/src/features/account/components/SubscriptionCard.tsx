"use client";

/** 구독 상태 카드 — Story 4.3 AC-2. Story 3.5 fetchCurrentSubscription 활용. */

import { useCurrentSubscription } from "@/features/billing/hooks/useCurrentSubscription";

import styles from "./SubscriptionCard.module.css";

interface SubscriptionCardProps {
  enabled?: boolean;
}

function formatKstDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const y = d.getUTCFullYear();
    // Pro 결제일은 KST 기준 +09:00 ISO이므로 단순 substring으로 충분.
    const isoKst = iso.slice(0, 10);
    return /^\d{4}-\d{2}-\d{2}$/.test(isoKst) ? isoKst : `${y}-??-??`;
  } catch {
    return iso;
  }
}

function scrollToPaymentHistory() {
  if (typeof document === "undefined") return;
  const el = document.getElementById("payment-history");
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

export function SubscriptionCard({ enabled = true }: SubscriptionCardProps) {
  const { data, isLoading, isError } = useCurrentSubscription({ enabled });

  if (isLoading) {
    return (
      <section className={styles.card} aria-label="구독 상태" aria-busy="true">
        <h2 className={styles.title}>구독 상태</h2>
        <p className={styles.placeholder}>불러오는 중…</p>
      </section>
    );
  }

  if (isError || !data) {
    return (
      <section className={styles.card} aria-label="구독 상태">
        <h2 className={styles.title}>구독 상태</h2>
        <p className={styles.placeholder}>불러오지 못했습니다 — 새로고침 해주세요.</p>
      </section>
    );
  }

  if (data.status === "none") {
    return null;
  }

  if (data.status === "active") {
    return (
      <section className={styles.card} aria-label="구독 상태">
        <h2 className={styles.title}>구독 상태</h2>
        <p className={styles.value}>
          구독 중 — 다음 결제일 {formatKstDate(data.next_charge_at ?? data.current_period_end)}
        </p>
        <button
          type="button"
          className={styles.manageBtn}
          onClick={scrollToPaymentHistory}
        >
          구독 관리
        </button>
      </section>
    );
  }

  // cancel_pending
  return (
    <section className={styles.card} aria-label="구독 상태">
      <h2 className={styles.title}>구독 상태</h2>
      <p className={styles.value}>
        해지 예정 ({formatKstDate(data.current_period_end)} 적용)
      </p>
      <button
        type="button"
        className={styles.manageBtn}
        onClick={scrollToPaymentHistory}
      >
        관리하기
      </button>
    </section>
  );
}
