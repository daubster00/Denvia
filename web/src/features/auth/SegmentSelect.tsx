"use client";

import { useState } from "react";
import { ApiError } from "@/types/api";

type SegmentValue = "doctor" | "hygienist" | "student_other";

interface SegmentSelectProps {
  onComplete: (segment: SegmentValue, yearsOfExperience?: number) => Promise<void>;
}

const SEGMENT_OPTIONS = [
  { value: "doctor" as const, label: "① 치과의사", needsYears: true },
  { value: "hygienist" as const, label: "② 치과위생사", needsYears: true },
  { value: "student_other" as const, label: "③ 치위생과 학생·기타", needsYears: false },
];

const btnBase: React.CSSProperties = {
  width: "100%",
  padding: "14px 16px",
  border: "1.5px solid #E1E2E4",
  borderRadius: 10,
  background: "#fff",
  fontSize: 15,
  fontWeight: 500,
  cursor: "pointer",
  textAlign: "left",
  transition: "border-color 0.15s",
};

/**
 * 가입유형 선택 컴포넌트 (F-106, UX-DR11).
 * 치과의사/위생사 선택 시 연차(1~50) 필수. 학생·기타는 연차 숨김.
 */
export function SegmentSelect({ onComplete }: SegmentSelectProps) {
  const [selected, setSelected] = useState<SegmentValue | null>(null);
  const [years, setYears] = useState<string>("");
  const [error, setError] = useState<string | undefined>();
  const [submitting, setSubmitting] = useState(false);

  const needsYears = selected !== null && selected !== "student_other";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selected) {
      setError("가입유형을 선택해주세요.");
      return;
    }
    if (needsYears) {
      const y = parseInt(years, 10);
      if (!years || isNaN(y) || y < 1 || y > 50) {
        setError("연차는 1~50 사이여야 합니다.");
        return;
      }
    }
    setError(undefined);
    setSubmitting(true);
    try {
      const yearsVal = needsYears ? parseInt(years, 10) : undefined;
      await onComplete(selected, yearsVal);
    } catch (e) {
      if (e instanceof ApiError) {
        setError(e.message);
      } else {
        setError("오류가 발생했습니다. 다시 시도해주세요.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} noValidate style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <p style={{ fontSize: 14, color: "#5A5C63", margin: "0 0 4px" }}>
        가입유형을 선택하면 맞춤 정보를 제공합니다.
      </p>

      {SEGMENT_OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => { setSelected(opt.value); setYears(""); setError(undefined); }}
          style={{
            ...btnBase,
            borderColor: selected === opt.value ? "#8B5CF6" : "#E1E2E4",
            background: selected === opt.value ? "#F5F3FF" : "#fff",
            color: selected === opt.value ? "#6D28D9" : "#171719",
          }}
        >
          {opt.label}
        </button>
      ))}

      {/* 조건부 연차 선택 */}
      {needsYears && (
        <div>
          <label htmlFor="years-select" style={{ display: "block", marginBottom: 4, fontSize: 14, fontWeight: 500 }}>
            연차 <span aria-label="필수" style={{ color: "#7C3AED" }}>*</span>
          </label>
          <select
            id="years-select"
            value={years}
            onChange={(e) => { setYears(e.target.value); setError(undefined); }}
            aria-invalid={!!error && !years}
            style={{
              width: "100%",
              padding: "10px 12px",
              border: `1px solid ${error && !years ? "#EF4444" : "#E1E2E4"}`,
              borderRadius: 8,
              fontSize: 14,
              background: "#fff",
              outline: "none",
              boxSizing: "border-box",
            }}
          >
            <option value="">연차를 선택하세요</option>
            {Array.from({ length: 50 }, (_, i) => i + 1).map((y) => (
              <option key={y} value={y}>{y}년차</option>
            ))}
          </select>
        </div>
      )}

      {error && (
        <p role="alert" style={{ color: "#EF4444", fontSize: 13 }}>{error}</p>
      )}

      <button
        type="submit"
        disabled={submitting || !selected}
        style={{
          padding: "13px 0",
          background: selected
            ? "linear-gradient(135deg, #8B5CF6 0%, #D946EF 100%)"
            : "#E1E2E4",
          color: selected ? "#fff" : "#AEB0B6",
          border: "none",
          borderRadius: 8,
          fontSize: 15,
          fontWeight: 600,
          cursor: selected ? "pointer" : "default",
          marginTop: 4,
        }}
      >
        {submitting ? "처리 중..." : "시작하기"}
      </button>
    </form>
  );
}
