"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/features/admin-content/api/popup";
import {
  fetchAnomalyThresholdsConfig,
  updateAnomalyThresholdsConfig,
  type AnomalyThresholdsResponse,
  type AnomalyThresholdsUpdateInput,
} from "@/features/admin-content/api/runtimeConfig";
import styles from "./page.module.css";

const QUERY_KEY = ["admin", "anomaly-thresholds"];

type Field = keyof AnomalyThresholdsUpdateInput;

interface RowSpec {
  field: Field;
  label: string;
  desc: string;
  unit: string;
  step: number;
}

interface CardSpec {
  title: string;
  effect: React.ReactNode;
  rows: RowSpec[];
}

// 페이지 구성 — 6 카테고리 11 항목.
// 각 카테고리의 "effect"는 사용자(비개발자) 기준으로 무엇을·얼마동안·어떻게 차단되는지 설명.
const CARDS: CardSpec[] = [
  {
    title: "1. 비밀번호 반복 실패",
    effect: (
      <>
        같은 이메일로 비밀번호가 <strong>실패 허용 횟수</strong>만큼 연속으로
        틀리면, 그 이메일의 로그인이 <strong>잠금 시간</strong> 동안 잠깁니다.
        잠금이 풀린 뒤 다시 한 번 더 틀리면 비밀번호 찾기를 사용할 때까지
        영구 잠금됩니다.
      </>
    ),
    rows: [
      {
        field: "login_brute_threshold",
        label: "실패 허용 횟수",
        desc: "이 횟수에 도달한 시도부터 잠금이 시작됩니다. 작을수록 엄격합니다.",
        unit: "회",
        step: 1,
      },
      {
        field: "login_lockout_seconds",
        label: "잠금 시간",
        desc: "초 단위로 입력합니다. 600 = 10분, 3600 = 1시간, 86400 = 24시간.",
        unit: "초",
        step: 60,
      },
    ],
  },
  {
    title: "2. 동일 IP 다중 로그인",
    effect: (
      <>
        같은 IP에서 서로 다른 계정이 <strong>추적 윈도우</strong> 안에{" "}
        <strong>동시 접속 계정 수</strong>만큼 로그인하면, 해당 IP와 연관된
        모든 사용자에 대해 이상탐지 이벤트가 기록되고 관리자에게 알림톡이
        발송됩니다. 자동 차단은 되지 않고, 관리자가 검토 후 직접 차단하는
        구조입니다.
      </>
    ),
    rows: [
      {
        field: "concurrent_ip_threshold",
        label: "동시 접속 계정 수",
        desc: "한 IP에서 윈도우 안에 합쳐서 N명이 로그인하면 의심으로 판단합니다.",
        unit: "명",
        step: 1,
      },
      {
        field: "concurrent_ip_window_seconds",
        label: "추적 윈도우",
        desc: "초 단위. 600 = 최근 10분 안에 N명 누적이면 의심.",
        unit: "초",
        step: 60,
      },
    ],
  },
  {
    title: "3. 동일 질문 반복",
    effect: (
      <>
        같은 질문 문장을 <strong>연속 반복 횟수</strong>만큼 보내면 해당
        사용자에게 자동 제한이 걸려, 관리자가 풀어주기 전까지 답변이 평소보다
        느리게 출력됩니다. 질문 자체는 계속 보낼 수 있습니다.
      </>
    ),
    rows: [
      {
        field: "repeated_question_threshold",
        label: "연속 반복 횟수",
        desc: "정확히 같은 텍스트가 연달아 이 횟수만큼 들어오면 자동 제한이 적용됩니다.",
        unit: "회",
        step: 1,
      },
    ],
  },
  {
    title: "4. 답변 직후 빠른 후속 질문",
    effect: (
      <>
        답변이 끝난 시점부터 <strong>시간 기준</strong> 안에 새 질문이 또
        들어오는 패턴이 <strong>연속 발생 횟수</strong>만큼 반복되면 해당
        사용자에게 자동 제한이 걸립니다. (관리자가 풀어주기 전까지 답변 지연)
      </>
    ),
    rows: [
      {
        field: "rapid_followup_window_seconds",
        label: "연속 답변 시간 기준",
        desc: "초 단위 (소수 가능). 3.0 = 답변 끝난 뒤 3초 안에 또 질문하면 1회 카운트.",
        unit: "초",
        step: 0.5,
      },
      {
        field: "rapid_followup_threshold",
        label: "연속 발생 횟수 기준",
        desc: "위 패턴이 이 횟수만큼 연달아 발생하면 자동 제한.",
        unit: "회",
        step: 1,
      },
    ],
  },
  {
    title: "5. 휴대폰 인증 남용",
    effect: (
      <>
        한 번호로 1시간 안에{" "}
        <strong>시간당 발송 허용 횟수</strong>를 초과해 OTP를 받으려 하면 그
        시점부터 1시간 동안 발송이 거절됩니다. 같은 1시간 안에 시도가{" "}
        <strong>24시간 차단 임계</strong>에 도달하면 그 번호는 <strong>24시간 동안</strong>{" "}
        모든 OTP 발송·검증이 막힙니다. <strong>인증번호 오답 허용 횟수</strong>는
        받은 OTP를 틀려도 되는 최대 횟수로, 초과 시 그 OTP는 무효화됩니다.
      </>
    ),
    rows: [
      {
        field: "sms_max_retries",
        label: "시간당 발송 허용 횟수",
        desc: "한 번호로 1시간 안에 N번까지 발송 가능. 이후 요청은 429.",
        unit: "회",
        step: 1,
      },
      {
        field: "sms_abuse_threshold",
        label: "시간당 24시간 차단 횟수",
        desc: "1시간 누적 시도 N회 도달 시 그 번호를 24시간 차단합니다.",
        unit: "회",
        step: 1,
      },
      {
        field: "sms_max_wrong",
        label: "인증번호 오답 허용 횟수",
        desc: "받은 OTP를 N번까지 틀려도 됩니다. 초과 시 OTP 즉시 무효화.",
        unit: "회",
        step: 1,
      },
    ],
  },
  {
    title: "6. 비밀번호·아이디 찾기 남용",
    effect: (
      <>
        한 번호로 1시간 안에 비밀번호/아이디 찾기를{" "}
        <strong>시간당 시도 허용 횟수</strong>만큼 시도하면 이상탐지 이벤트가
        기록되고 관리자에게 알림톡이 발송됩니다. 사용자 측 차단은 별도로 걸지
        않습니다.
      </>
    ),
    rows: [
      {
        field: "recovery_abuse_threshold",
        label: "시간당 찾기 시도 허용 횟수",
        desc: "한 번호로 1시간 안에 N번 시도 시 의심으로 판단합니다.",
        unit: "회",
        step: 1,
      },
    ],
  },
];

function buildFormFromResponse(
  data: AnomalyThresholdsResponse,
): AnomalyThresholdsUpdateInput {
  return {
    login_brute_threshold: data.login_brute_threshold.current,
    login_lockout_seconds: data.login_lockout_seconds.current,
    concurrent_ip_threshold: data.concurrent_ip_threshold.current,
    concurrent_ip_window_seconds: data.concurrent_ip_window_seconds.current,
    repeated_question_threshold: data.repeated_question_threshold.current,
    rapid_followup_window_seconds: data.rapid_followup_window_seconds.current,
    rapid_followup_threshold: data.rapid_followup_threshold.current,
    sms_max_retries: data.sms_max_retries.current,
    sms_abuse_threshold: data.sms_abuse_threshold.current,
    sms_max_wrong: data.sms_max_wrong.current,
    recovery_abuse_threshold: data.recovery_abuse_threshold.current,
  };
}

function buildDefaultsFromResponse(
  data: AnomalyThresholdsResponse,
): AnomalyThresholdsUpdateInput {
  return {
    login_brute_threshold: data.login_brute_threshold.default,
    login_lockout_seconds: data.login_lockout_seconds.default,
    concurrent_ip_threshold: data.concurrent_ip_threshold.default,
    concurrent_ip_window_seconds: data.concurrent_ip_window_seconds.default,
    repeated_question_threshold: data.repeated_question_threshold.default,
    rapid_followup_window_seconds: data.rapid_followup_window_seconds.default,
    rapid_followup_threshold: data.rapid_followup_threshold.default,
    sms_max_retries: data.sms_max_retries.default,
    sms_abuse_threshold: data.sms_abuse_threshold.default,
    sms_max_wrong: data.sms_max_wrong.default,
    recovery_abuse_threshold: data.recovery_abuse_threshold.default,
  };
}

function isFormEqual(
  a: AnomalyThresholdsUpdateInput,
  b: AnomalyThresholdsUpdateInput,
): boolean {
  return (Object.keys(a) as Field[]).every((k) => a[k] === b[k]);
}

export default function AnomalyThresholdsPage() {
  const queryClient = useQueryClient();
  const configQuery = useQuery({
    queryKey: QUERY_KEY,
    queryFn: fetchAnomalyThresholdsConfig,
  });

  const [formDraft, setFormDraft] =
    useState<AnomalyThresholdsUpdateInput | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<Field, string>>>(
    {},
  );
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const responseForm = useMemo(
    () =>
      configQuery.data ? buildFormFromResponse(configQuery.data) : null,
    [configQuery.data],
  );
  const form = formDraft ?? responseForm;

  const saveMutation = useMutation({
    mutationFn: updateAnomalyThresholdsConfig,
    onSuccess: (data) => {
      setSavedAt(Date.now());
      setSubmitError(null);
      setFormDraft(buildFormFromResponse(data));
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

  const isDirty = useMemo(() => {
    if (!form || !configQuery.data) return false;
    return !isFormEqual(form, buildFormFromResponse(configQuery.data));
  }, [form, configQuery.data]);

  const onChange = (field: Field, raw: string, min: number) => {
    setSavedAt(null);
    setSubmitError(null);
    setFieldErrors((prev) => ({ ...prev, [field]: undefined }));
    const value = raw === "" ? min : Number(raw);
    setFormDraft((prev) => {
      const base = prev ?? form;
      return base ? { ...base, [field]: value } : prev;
    });
  };

  const onReset = () => {
    if (!configQuery.data) return;
    setFormDraft(buildDefaultsFromResponse(configQuery.data));
    setFieldErrors({});
    setSavedAt(null);
    setSubmitError(null);
  };

  const onSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!form || !configQuery.data) return;

    // 각 항목 범위 검증.
    const errors: Partial<Record<Field, string>> = {};
    for (const card of CARDS) {
      for (const row of card.rows) {
        const meta = configQuery.data[row.field];
        const value = form[row.field];
        if (Number.isNaN(value)) {
          errors[row.field] = "숫자를 입력해주세요.";
          continue;
        }
        if (value < meta.min) {
          errors[row.field] = `${meta.min} 이상이어야 합니다.`;
          continue;
        }
        if (value > meta.max) {
          errors[row.field] = `${meta.max} 이하여야 합니다.`;
        }
      }
    }
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    saveMutation.mutate(form);
  };

  if (configQuery.isPending) {
    return (
      <main className={styles.page}>
        <div className={styles.loading} role="status">
          설정 불러오는 중…
        </div>
      </main>
    );
  }

  if (configQuery.error || !configQuery.data || !form) {
    return (
      <main className={styles.page}>
        <div className={styles.errorBox} role="alert">
          설정을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.
        </div>
      </main>
    );
  }

  const data = configQuery.data;

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.heading}>이상탐지 — 탐지 기준 설정</h1>
        <p className={styles.subheading}>
          이상탐지 6종의 발동 기준을 조정합니다. 작을수록 엄격하고 클수록
          느슨합니다. 각 카테고리 아래의 안내는 그 항목이 발동했을 때 사용자가
          어떻게 차단·제한되는지를 설명합니다.
        </p>
        <div className={styles.applyHint}>
          저장 즉시 반영됩니다. 서버 재시작·재배포 없이 다음 발생부터 새
          기준으로 동작합니다.
        </div>
      </header>

      <form className={styles.formStack} onSubmit={onSubmit}>
        {CARDS.map((card) => (
          <section key={card.title} className={styles.formCard}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>{card.title}</h2>
              <p className={styles.cardEffect}>{card.effect}</p>
            </div>

            {card.rows.map((row) => {
              const meta = data[row.field];
              const value = form[row.field];
              const err = fieldErrors[row.field];
              return (
                <div key={row.field} className={styles.row}>
                  <div className={styles.rowText}>
                    <span className={styles.rowLabel}>{row.label}</span>
                    <span className={styles.rowDesc}>
                      {row.desc} 입력 가능 범위 {meta.min}~{meta.max}{row.unit}.
                      기본값 {meta.default}
                      {row.unit}.
                    </span>
                    {err ? (
                      <span className={styles.fieldError} role="alert">
                        {err}
                      </span>
                    ) : null}
                  </div>
                  <div className={styles.numberCell}>
                    <input
                      type="number"
                      min={meta.min}
                      max={meta.max}
                      step={row.step}
                      className={styles.numberInput}
                      value={value}
                      onChange={(e) =>
                        onChange(row.field, e.target.value, meta.min)
                      }
                      aria-label={row.label}
                    />
                    <span className={styles.unit}>{row.unit}</span>
                  </div>
                </div>
              );
            })}
          </section>
        ))}

        <div className={styles.footer}>
          <div
            className={
              submitError
                ? `${styles.statusText} ${styles.error}`
                : savedAt && !isDirty
                  ? `${styles.statusText} ${styles.success}`
                  : isDirty
                    ? `${styles.statusText} ${styles.dirty}`
                    : styles.statusText
            }
            role={submitError ? "alert" : "status"}
          >
            {submitError
              ? submitError
              : savedAt && !isDirty
                ? "저장되었습니다."
                : isDirty
                  ? "변경사항이 있습니다. 저장을 눌러 적용하세요."
                  : ""}
          </div>
          <div className={styles.actions}>
            <button
              type="button"
              className={styles.resetBtn}
              onClick={onReset}
              disabled={saveMutation.isPending}
            >
              전체 기본값
            </button>
            <button
              type="submit"
              className={styles.saveBtn}
              disabled={!isDirty || saveMutation.isPending}
            >
              {saveMutation.isPending ? "저장 중…" : "저장"}
            </button>
          </div>
        </div>
      </form>
    </main>
  );
}
