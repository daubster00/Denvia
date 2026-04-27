"use client";

import { useRouter } from "next/navigation";
import { useQuotaStore } from "@/stores/quota-store";
import styles from "./QuotaLock.module.css";

export function QuotaLock() {
  const { locked, payload, dismiss } = useQuotaStore();
  const router = useRouter();

  if (!locked || !payload) return null;

  const isInternal = payload.reason === "QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT";
  const headline = isInternal
    ? "일시적 시스템 보호 제한에 도달했습니다."
    : `오늘의 ${payload.dailyLimit}회를 모두 사용했어요.`;
  const body = isInternal
    ? "고객문의로 연락주세요."
    : "내일 다시 오시거나, Pro로 계속 진료에 활용해보세요.";

  return (
    <div role="alert" className={styles.lock}>
      <div className={styles.headRow}>
        <span aria-hidden="true">잠금</span>
        <strong className={styles.head}>{headline}</strong>
      </div>
      <p className={styles.body}>{body}</p>
      <div className={styles.actions}>
        {!isInternal && (
          <button
            type="button"
            onClick={dismiss}
            className={styles.tomorrowBtn}
          >
            내일 다시
          </button>
        )}
        {!isInternal && payload.showUpgradePrompt && payload.showSubscribeButton && (
          <button
            type="button"
            onClick={() => router.push("/subscribe")}
            className={styles.upgradeBtn}
          >
            Pro로 계속
          </button>
        )}
      </div>
    </div>
  );
}
