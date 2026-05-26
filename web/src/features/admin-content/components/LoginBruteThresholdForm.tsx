"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/features/admin-content/api/popup";
import {
  LoginBruteThresholdFormInput,
  loginBruteThresholdFormSchema,
  fetchLoginBruteThresholdConfig,
  updateLoginBruteThresholdConfig,
} from "@/features/admin-content/api/runtimeConfig";
import styles from "./ServiceTogglesForm.module.css";

const QUERY_KEY = ["admin", "login-brute-threshold"];

const EMPTY_FORM: LoginBruteThresholdFormInput = {
  threshold: 3,
};

export function LoginBruteThresholdForm() {
  const queryClient = useQueryClient();
  const configQuery = useQuery({
    queryKey: QUERY_KEY,
    queryFn: fetchLoginBruteThresholdConfig,
  });

  const [form, setForm] = useState<LoginBruteThresholdFormInput>(EMPTY_FORM);
  const [errors, setErrors] = useState<
    Partial<Record<keyof LoginBruteThresholdFormInput, string>>
  >({});
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (configQuery.data) {
      setForm({ threshold: configQuery.data.threshold });
    }
  }, [configQuery.data]);

  const isDirty = configQuery.data
    ? form.threshold !== configQuery.data.threshold
    : false;

  const saveMutation = useMutation({
    mutationFn: updateLoginBruteThresholdConfig,
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
    const parsed = loginBruteThresholdFormSchema.safeParse(form);
    if (!parsed.success) {
      const fieldErrors: typeof errors = {};
      for (const issue of parsed.error.issues) {
        const field = issue.path[0] as keyof LoginBruteThresholdFormInput;
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

  const min = configQuery.data?.min_threshold ?? 1;
  const max = configQuery.data?.max_threshold ?? 20;
  const defaultThreshold = configQuery.data?.default_threshold ?? 3;

  return (
    <section
      className={styles.card}
      aria-labelledby="login-brute-threshold-heading"
    >
      <header className={styles.header}>
        <h2 id="login-brute-threshold-heading" className={styles.heading}>
          로그인 실패 이상탐지 기준
        </h2>
        <p className={styles.subheading}>
          같은 이메일로 비밀번호를 연속으로 틀린 횟수가 아래 값에 도달하면,
          이상탐지 이벤트가 기록되고 해당 이메일이 10분간 자동으로 잠깁니다.
          숫자가 작을수록 엄격하고, 클수록 느슨합니다. 권장 기본값은
          {" "}
          {defaultThreshold}회입니다.
        </p>
      </header>

      <form className={styles.form} onSubmit={onSubmit}>
        <div className={styles.row}>
          <div className={styles.rowText}>
            <span className={styles.rowLabel}>연속 실패 허용 횟수</span>
            <span className={styles.rowDesc}>
              {min}회 이상 {max}회 이하로 설정할 수 있습니다. 이 값에 도달한
              요청부터 잠금이 시작됩니다(예: 3으로 두면 3번째 실패에서 잠금).
            </span>
          </div>
          <div className={styles.numberCell}>
            <input
              type="number"
              min={min}
              max={max}
              step={1}
              className={styles.numberInput}
              value={form.threshold}
              onChange={(e) =>
                setForm({
                  threshold:
                    e.target.value === "" ? min : Number(e.target.value),
                })
              }
              aria-label="로그인 실패 이상탐지 기준 횟수"
            />
            <span className={styles.unit}>회</span>
          </div>
        </div>
        {errors.threshold ? (
          <p className={styles.fieldError} role="alert">
            {errors.threshold}
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
