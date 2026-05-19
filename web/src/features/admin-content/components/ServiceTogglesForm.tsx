"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/features/admin-content/api/popup";
import {
  RuntimeConfigFormInput,
  fetchRuntimeConfig,
  runtimeConfigFormSchema,
  updateRuntimeConfig,
} from "@/features/admin-content/api/runtimeConfig";
import styles from "./ServiceTogglesForm.module.css";

const QUERY_KEY = ["admin", "runtime-config"];

const EMPTY_FORM: RuntimeConfigFormInput = {
  show_subscribe_button: true,
  free_daily_quota: 10,
  free_delay_enabled: true,
  free_delay_seconds: 1,
};

export function ServiceTogglesForm() {
  const queryClient = useQueryClient();
  const configQuery = useQuery({
    queryKey: QUERY_KEY,
    queryFn: fetchRuntimeConfig,
  });

  const [form, setForm] = useState<RuntimeConfigFormInput>(EMPTY_FORM);
  const [errors, setErrors] = useState<Partial<Record<keyof RuntimeConfigFormInput, string>>>({});
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (configQuery.data) {
      setForm({
        show_subscribe_button: configQuery.data.show_subscribe_button,
        free_daily_quota: configQuery.data.free_daily_quota,
        free_delay_enabled: configQuery.data.free_delay_enabled,
        free_delay_seconds: configQuery.data.free_delay_seconds,
      });
    }
  }, [configQuery.data]);

  const isDirty = configQuery.data
    ? form.show_subscribe_button !== configQuery.data.show_subscribe_button ||
      form.free_daily_quota !== configQuery.data.free_daily_quota ||
      form.free_delay_enabled !== configQuery.data.free_delay_enabled ||
      form.free_delay_seconds !== configQuery.data.free_delay_seconds
    : false;

  const saveMutation = useMutation({
    mutationFn: updateRuntimeConfig,
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
    const parsed = runtimeConfigFormSchema.safeParse(form);
    if (!parsed.success) {
      const fieldErrors: typeof errors = {};
      for (const issue of parsed.error.issues) {
        const field = issue.path[0] as keyof RuntimeConfigFormInput;
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
    <section className={styles.card} aria-labelledby="service-toggles-heading">
      <header className={styles.header}>
        <h2 id="service-toggles-heading" className={styles.heading}>
          서비스 전체 토글
        </h2>
        <p className={styles.subheading}>
          전체 사용자에게 즉시 반영됩니다. 저장 버튼을 눌러야 적용됩니다.
        </p>
      </header>

      <form className={styles.form} onSubmit={onSubmit}>
        <div className={styles.row}>
          <div className={styles.rowText}>
            <span className={styles.rowLabel}>구독 버튼 노출</span>
            <span className={styles.rowDesc}>
              로그인 후 우측 상단 “구독” 버튼과 마이페이지 “구독하기” 버튼을 모두 가립니다. OFF여도 결제 페이지 자체는 살아 있습니다.
            </span>
          </div>
          <ToggleSwitch
            ariaLabel="구독 버튼 노출"
            checked={form.show_subscribe_button}
            onChange={(v) =>
              setForm((p) => ({ ...p, show_subscribe_button: v }))
            }
          />
        </div>

        <div className={styles.row}>
          <div className={styles.rowText}>
            <span className={styles.rowLabel}>1일 무료 질문 횟수</span>
            <span className={styles.rowDesc}>
              구독하지 않은 모든 사용자에게 적용되는 하루 기본 질문 가능 횟수입니다. (0~9999)
            </span>
          </div>
          <div className={styles.numberCell}>
            <input
              type="number"
              min={0}
              max={9999}
              step={1}
              className={styles.numberInput}
              value={form.free_daily_quota}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  free_daily_quota: Number(e.target.value),
                }))
              }
              aria-label="1일 무료 질문 횟수"
            />
            <span className={styles.unit}>회</span>
          </div>
        </div>
        {errors.free_daily_quota ? (
          <p className={styles.fieldError} role="alert">
            {errors.free_daily_quota}
          </p>
        ) : null}

        <div className={styles.row}>
          <div className={styles.rowText}>
            <span className={styles.rowLabel}>답변 속도(지연) 사용</span>
            <span className={styles.rowDesc}>
              무료 사용자가 질문할 때 답변이 천천히 출력되도록 의도적 지연을 켜고 끕니다. OFF면 즉시 출력됩니다.
            </span>
          </div>
          <ToggleSwitch
            ariaLabel="답변 속도 ON/OFF"
            checked={form.free_delay_enabled}
            onChange={(v) =>
              setForm((p) => ({ ...p, free_delay_enabled: v }))
            }
          />
        </div>

        <div className={styles.row}>
          <div className={styles.rowText}>
            <span className={styles.rowLabel}>답변 지연 시간</span>
            <span className={styles.rowDesc}>
              위 토글이 ON일 때 적용되는 지연 시간(초)입니다. 0초 이상으로 자유롭게 입력하세요.
            </span>
          </div>
          <div className={styles.numberCell}>
            <input
              type="number"
              min={0}
              step={1}
              className={styles.numberInput}
              value={form.free_delay_seconds}
              disabled={!form.free_delay_enabled}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  free_delay_seconds: Number(e.target.value),
                }))
              }
              aria-label="답변 지연 시간 (초)"
            />
            <span className={styles.unit}>초</span>
          </div>
        </div>
        {errors.free_delay_seconds ? (
          <p className={styles.fieldError} role="alert">
            {errors.free_delay_seconds}
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
