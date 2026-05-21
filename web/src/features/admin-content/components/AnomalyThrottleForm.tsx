"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/features/admin-content/api/popup";
import {
  AnomalyThrottleFormInput,
  anomalyThrottleFormSchema,
  fetchAnomalyThrottleConfig,
  updateAnomalyThrottleConfig,
} from "@/features/admin-content/api/runtimeConfig";
import styles from "./ServiceTogglesForm.module.css";

const QUERY_KEY = ["admin", "anomaly-throttle"];

const EMPTY_FORM: AnomalyThrottleFormInput = {
  enabled: true,
  free_delay_seconds: 5,
  pro_delay_seconds: 2,
};

export function AnomalyThrottleForm() {
  const queryClient = useQueryClient();
  const configQuery = useQuery({
    queryKey: QUERY_KEY,
    queryFn: fetchAnomalyThrottleConfig,
  });

  const [form, setForm] = useState<AnomalyThrottleFormInput>(EMPTY_FORM);
  const [errors, setErrors] = useState<
    Partial<Record<keyof AnomalyThrottleFormInput, string>>
  >({});
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (configQuery.data) {
      setForm({
        enabled: configQuery.data.enabled,
        free_delay_seconds: configQuery.data.free_delay_seconds,
        pro_delay_seconds: configQuery.data.pro_delay_seconds,
      });
    }
  }, [configQuery.data]);

  const isDirty = configQuery.data
    ? form.enabled !== configQuery.data.enabled ||
      form.free_delay_seconds !== configQuery.data.free_delay_seconds ||
      form.pro_delay_seconds !== configQuery.data.pro_delay_seconds
    : false;

  const saveMutation = useMutation({
    mutationFn: updateAnomalyThrottleConfig,
    onSuccess: (data) => {
      setSavedAt(Date.now());
      setSubmitError(null);
      queryClient.setQueryData(QUERY_KEY, data);
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError) {
        setSubmitError(err.message);
      } else {
        setSubmitError("저장에 실패했습니다.");
      }
    },
  });

  const onSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const parsed = anomalyThrottleFormSchema.safeParse(form);
    if (!parsed.success) {
      const fieldErrors: typeof errors = {};
      for (const issue of parsed.error.issues) {
        const field = issue.path[0] as keyof AnomalyThrottleFormInput;
        if (!fieldErrors[field]) fieldErrors[field] = issue.message;
      }
      setErrors(fieldErrors);
      return;
    }
    setErrors({});
    saveMutation.mutate(parsed.data);
  };

  if (configQuery.isPending) {
    return (
      <section className={styles.card}>
        <p className={styles.loading} role="status">
          설정 불러오는 중…
        </p>
      </section>
    );
  }

  if (configQuery.error) {
    return (
      <section className={styles.card}>
        <p className={styles.error} role="alert">
          설정을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.
        </p>
      </section>
    );
  }

  return (
    <section className={styles.card} aria-labelledby="anomaly-throttle-heading">
      <header className={styles.header}>
        <h2 id="anomaly-throttle-heading" className={styles.heading}>
          이상 질문 패턴 자동 속도 제한
        </h2>
        <p className={styles.subheading}>
          답변이 완료된 직후 3초 안에 다음 질문을 또 누르는 행동이 연속 3회
          관측되면, 해당 계정의 답변 시작 속도를 아래 값으로 자동 제한합니다.
          무료 사용자에게는 안내 팝업이 함께 노출됩니다. 한 번 적용되면
          사용자 상세 화면에서 관리자가 직접 풀 때까지 유지됩니다.
        </p>
      </header>

      <form className={styles.form} onSubmit={onSubmit}>
        <div className={styles.row}>
          <div className={styles.rowText}>
            <span className={styles.rowLabel}>자동 속도 제한 사용</span>
            <span className={styles.rowDesc}>
              OFF로 두면 탐지는 계속 기록되지만 답변 속도는 제한하지 않습니다.
              긴급 점검 시 OFF.
            </span>
          </div>
          <ToggleSwitch
            ariaLabel="자동 속도 제한 ON/OFF"
            checked={form.enabled}
            onChange={(v) => setForm((p) => ({ ...p, enabled: v }))}
          />
        </div>

        <div className={styles.row}>
          <div className={styles.rowText}>
            <span className={styles.rowLabel}>무료 사용자 제한 지연</span>
            <span className={styles.rowDesc}>
              탐지된 무료 사용자의 답변이 시작되기 전 기다리는 시간(초). 0.1초
              단위. 보통 무료 기본 지연보다 길게 잡습니다.
            </span>
          </div>
          <div className={styles.numberCell}>
            <input
              type="number"
              min={0}
              max={999.9}
              step={0.1}
              className={styles.numberInput}
              value={
                form.free_delay_seconds === 0 ? "" : form.free_delay_seconds
              }
              placeholder="0"
              disabled={!form.enabled}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  free_delay_seconds:
                    e.target.value === "" ? 0 : Number(e.target.value),
                }))
              }
              aria-label="무료 사용자 제한 지연 (초)"
            />
            <span className={styles.unit}>초</span>
          </div>
        </div>
        {errors.free_delay_seconds ? (
          <p className={styles.fieldError} role="alert">
            {errors.free_delay_seconds}
          </p>
        ) : null}

        <div className={styles.row}>
          <div className={styles.rowText}>
            <span className={styles.rowLabel}>유료 사용자 제한 지연</span>
            <span className={styles.rowDesc}>
              탐지된 유료 사용자의 답변 시작 지연(초). 결제자 보호 차원에서
              무료보다 짧게 두는 편이 일반적입니다. 팝업은 무료에만 노출됩니다.
            </span>
          </div>
          <div className={styles.numberCell}>
            <input
              type="number"
              min={0}
              max={999.9}
              step={0.1}
              className={styles.numberInput}
              value={
                form.pro_delay_seconds === 0 ? "" : form.pro_delay_seconds
              }
              placeholder="0"
              disabled={!form.enabled}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  pro_delay_seconds:
                    e.target.value === "" ? 0 : Number(e.target.value),
                }))
              }
              aria-label="유료 사용자 제한 지연 (초)"
            />
            <span className={styles.unit}>초</span>
          </div>
        </div>
        {errors.pro_delay_seconds ? (
          <p className={styles.fieldError} role="alert">
            {errors.pro_delay_seconds}
          </p>
        ) : null}

        <div className={styles.footer}>
          {submitError ? (
            <p className={styles.error} role="alert">
              {submitError}
            </p>
          ) : savedAt ? (
            <p className={styles.success} role="status">
              저장되었습니다.
            </p>
          ) : (
            <span aria-hidden="true" />
          )}
          <button
            type="submit"
            className={styles.saveBtn}
            disabled={!isDirty || saveMutation.isPending}
          >
            {saveMutation.isPending ? "저장 중…" : "저장"}
          </button>
        </div>
      </form>
    </section>
  );
}

interface ToggleSwitchProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  ariaLabel: string;
}

function ToggleSwitch({ checked, onChange, ariaLabel }: ToggleSwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      onClick={() => onChange(!checked)}
      className={`${styles.toggle} ${checked ? styles.toggleOn : ""}`}
    >
      <span className={styles.toggleThumb} aria-hidden="true" />
      <span className={styles.toggleText} aria-hidden="true">
        {checked ? "ON" : "OFF"}
      </span>
    </button>
  );
}
