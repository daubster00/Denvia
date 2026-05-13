"use client";

import {
  type InquiryStatus,
  INQUIRY_STATUS_LABELS,
} from "../api";
import styles from "./InquiryStatusBadge.module.css";

interface Props {
  status: InquiryStatus;
}

const STATUS_CLASS: Record<InquiryStatus, string> = {
  open: styles.open,
  in_progress: styles.inProgress,
  resolved: styles.resolved,
};

export function InquiryStatusBadge({ status }: Props) {
  return (
    <span className={`${styles.badge} ${STATUS_CLASS[status]}`}>
      {INQUIRY_STATUS_LABELS[status]}
    </span>
  );
}
