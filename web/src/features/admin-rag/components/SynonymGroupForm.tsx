"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { synonymGroupSchema, type SynonymGroupInput } from "../api/synonyms";
import type { SynonymGroup } from "../api/synonyms";
import styles from "./SynonymGroupForm.module.css";

interface Props {
  initial?: SynonymGroup;
  occupiedTerms?: Map<string, { id: number; canonicalTerm: string }>;
  submitting?: boolean;
  error?: string | null;
  onSubmit: (data: SynonymGroupInput) => void;
  onCancel: () => void;
  submitLabel?: string;
}

interface SynonymChipState {
  value: string;
  conflict?: { canonicalTerm: string };
}

export function SynonymGroupForm({
  initial,
  occupiedTerms,
  submitting = false,
  error = null,
  onSubmit,
  onCancel,
  submitLabel = "저장",
}: Props) {
  const ownId = initial?.id ?? null;
  const occupied = occupiedTerms ?? new Map<string, { id: number; canonicalTerm: string }>();

  const {
    register,
    handleSubmit,
    control,
    watch,
    formState: { errors, isDirty },
  } = useForm<SynonymGroupInput>({
    resolver: zodResolver(synonymGroupSchema),
    defaultValues: {
      canonical_term: initial?.canonical_term ?? "",
      synonyms: initial?.synonyms ?? [],
    },
  });

  const canonicalTerm = watch("canonical_term");
  const synonyms = watch("synonyms");

  const canonicalConflict = useMemo(() => {
    const term = (canonicalTerm ?? "").trim();
    if (!term) return null;
    const owner = occupied.get(term);
    if (!owner || owner.id === ownId) return null;
    return owner;
  }, [canonicalTerm, occupied, ownId]);

  const chipStates: SynonymChipState[] = useMemo(() => {
    return (synonyms ?? []).map((s) => {
      const owner = occupied.get(s);
      const conflictsWithOther = owner && owner.id !== ownId;
      return {
        value: s,
        conflict: conflictsWithOther
          ? { canonicalTerm: owner.canonicalTerm }
          : undefined,
      };
    });
  }, [synonyms, occupied, ownId]);

  return (
    <form className={styles.form} onSubmit={handleSubmit(onSubmit)} noValidate>
      <div className={styles.field}>
        <label className={styles.label} htmlFor="canonical-term-input">
          대표어
        </label>
        <input
          id="canonical-term-input"
          type="text"
          className={styles.input}
          placeholder="예: 광중합기"
          {...register("canonical_term")}
        />
        {errors.canonical_term && (
          <p className={styles.error}>{errors.canonical_term.message}</p>
        )}
        {canonicalConflict && (
          <p className={styles.warn} role="status">
            ⚠️ 이미 그룹 &quot;{canonicalConflict.canonicalTerm}&quot;에 있는 표현입니다.
          </p>
        )}
      </div>

      <Controller
        name="synonyms"
        control={control}
        render={({ field }) => (
          <SynonymChipInput
            value={field.value ?? []}
            chipStates={chipStates}
            onChange={field.onChange}
            disabled={submitting}
          />
        )}
      />
      {errors.synonyms && (
        <p className={styles.error}>
          {errors.synonyms.message ??
            (Array.isArray(errors.synonyms)
              ? errors.synonyms.find((e) => e?.message)?.message ?? "입력값 확인"
              : "입력값 확인")}
        </p>
      )}

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.actions}>
        <button
          type="button"
          className={styles.cancelBtn}
          onClick={onCancel}
          disabled={submitting}
        >
          취소
        </button>
        <button
          type="submit"
          className={styles.saveBtn}
          disabled={submitting || (!isDirty && initial !== undefined)}
        >
          {submitting ? "저장 중..." : submitLabel}
        </button>
      </div>
    </form>
  );
}

interface ChipInputProps {
  value: string[];
  chipStates: SynonymChipState[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}

function SynonymChipInput({ value, chipStates, onChange, disabled }: ChipInputProps) {
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  // chipStates 우선 사용 (parent의 충돌 상태 포함). 기본은 value.
  const states: SynonymChipState[] =
    chipStates.length === value.length
      ? chipStates
      : value.map((v) => ({ value: v }));

  useEffect(() => {
    setDraft("");
  }, [value.length]);

  const commit = (raw: string) => {
    const next = raw.trim();
    if (!next) return;
    if (value.includes(next)) {
      setDraft("");
      return;
    }
    onChange([...value, next]);
    setDraft("");
  };

  const removeAt = (idx: number) => {
    const next = [...value];
    next.splice(idx, 1);
    onChange(next);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit(draft);
    } else if (e.key === "Backspace" && !draft && value.length > 0) {
      e.preventDefault();
      removeAt(value.length - 1);
    }
  };

  return (
    <div className={styles.field}>
      <label className={styles.label}>동의어 (Enter로 추가)</label>
      <div
        className={styles.chipArea}
        onClick={() => inputRef.current?.focus()}
        role="presentation"
      >
        {states.map((chip, idx) => (
          <span
            key={`${chip.value}-${idx}`}
            className={`${styles.chip} ${chip.conflict ? styles.chipConflict : ""}`}
            title={
              chip.conflict
                ? `이미 그룹 '${chip.conflict.canonicalTerm}'에 있습니다`
                : undefined
            }
          >
            <span className={styles.chipText}>{chip.value}</span>
            <button
              type="button"
              className={styles.chipRemove}
              aria-label={`${chip.value} 제거`}
              onClick={(e) => {
                e.stopPropagation();
                removeAt(idx);
              }}
              disabled={disabled}
            >
              ×
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          type="text"
          className={styles.chipInput}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={() => commit(draft)}
          placeholder={value.length === 0 ? "예: 큐링기" : ""}
          disabled={disabled}
        />
      </div>
    </div>
  );
}
