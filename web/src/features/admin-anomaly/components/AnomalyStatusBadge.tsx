import type { AnomalyStatus } from "@/features/admin-anomaly/api/anomaly";
import styles from "./AnomalyStatusBadge.module.css";

interface Props {
  status: AnomalyStatus;
}

const LABELS: Record<AnomalyStatus, string> = {
  new: "신규",
  reviewed: "검토 완료",
  actioned: "차단 적용",
};

export function AnomalyStatusBadge({ status }: Props) {
  const cls =
    status === "actioned"
      ? styles.warning
      : status === "reviewed"
        ? styles.success
        : styles.brand;
  return (
    <span className={cls} data-testid={`anomaly-status-${status}`}>
      {LABELS[status]}
    </span>
  );
}
