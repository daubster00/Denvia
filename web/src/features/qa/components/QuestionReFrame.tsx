"use client";

import styles from "./QuestionReFrame.module.css";

// UX-DR26 마이크로카피 — 단일 상수, 매 렌더 랜덤화 금지
const SECTION_HEADLINE = "새 질문에 포함해보세요";

interface QuestionReFrameProps {
  options: string[];
  onPickOption: (option: string) => void;
}

export function QuestionReFrame({ options, onPickOption }: QuestionReFrameProps) {
  return (
    <div role="status" aria-live="polite" className={styles.container}>
      <div className={styles.headline}>
        <span aria-hidden="true" className={styles.emoji}>
          💡
        </span>
        <span>{SECTION_HEADLINE}</span>
      </div>
      <div className={styles.chipRow}>
        {options.map((opt) => (
          <button
            key={opt}
            type="button"
            aria-label={`새 질문에 넣기: ${opt}`}
            onClick={() => onPickOption(opt)}
            className={styles.chip}
          >
            {opt}
          </button>
        ))}
      </div>
    </div>
  );
}
