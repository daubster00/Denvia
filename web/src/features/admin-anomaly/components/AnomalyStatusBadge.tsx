import type { AnomalyStatus } from "@/features/admin-anomaly/api/anomaly";
import styles from "./AnomalyStatusBadge.module.css";

interface Props {
  status: AnomalyStatus;
  /**
   * 대상 사용자에게 "지금" 관리자 수동 차단(24h/7d/영구/질문전용)이 활성인지.
   */
  blockedNow?: boolean;
  /**
   * 대상 사용자에게 "지금" 시스템 자동제한(anomaly_throttled_at 또는 login_brute_force Redis 락아웃)이 활성인지.
   */
  throttledNow?: boolean;
}

// 라벨 결정 규칙(사용자 요구 2026-05-22):
//   차단 O + 제한 O → '차단 및 제한'
//   차단 O + 제한 X → '차단'
//   차단 X + 제한 O → '자동제한'
//   둘 다 X + status='new'   → '검토필요'   (아직 한 번도 처리 안 됨)
//   둘 다 X + status≠'new'   → '해제'       (한 번 걸렸다가 풀린 상태)
export function AnomalyStatusBadge({
  status,
  blockedNow = false,
  throttledNow = false,
}: Props) {
  let label: string;
  let cls: string;
  let testKey: string;

  if (blockedNow && throttledNow) {
    label = "차단 및 제한";
    cls = styles.warning;
    testKey = "blocked-throttled";
  } else if (blockedNow) {
    label = "차단";
    cls = styles.warning;
    testKey = "blocked";
  } else if (throttledNow) {
    label = "자동제한";
    cls = styles.info;
    testKey = "auto-throttle";
  } else if (status === "new") {
    label = "검토필요";
    cls = styles.brand;
    testKey = "needs-review";
  } else {
    label = "해제";
    cls = styles.success;
    testKey = "resolved";
  }

  return (
    <span className={cls} data-testid={`anomaly-status-${testKey}`}>
      {label}
    </span>
  );
}
