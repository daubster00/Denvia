"use client";

import { DashboardWidget } from "./DashboardWidget";
import styles from "./ComingSoonWidget.module.css";

interface ComingSoonWidgetProps {
  title: string;
  description: string;
  storyRef: string;
  placeholderHint?: string;
  detailDisabledTitle?: string;
}

export function ComingSoonWidget({
  title,
  description,
  storyRef,
  placeholderHint = "데이터가 연결되면 여기에 차트가 표시됩니다.",
  detailDisabledTitle,
}: ComingSoonWidgetProps) {
  return (
    <DashboardWidget
      title={title}
      tone="coming-soon"
      detailDisabledTitle={detailDisabledTitle ?? storyRef}
    >
      <div className={styles.body}>
        <p className={styles.summary}>{description}</p>
        <div
          className={styles.placeholder}
          role="img"
          aria-label={`${title} 차트 자리 (준비 중)`}
        >
          {placeholderHint}
        </div>
        <p className={styles.storyRef}>{storyRef}</p>
      </div>
    </DashboardWidget>
  );
}
