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
  free_delay_notice_text: "",
  pro_monthly_quota: 500,
  qa_notice_enabled: true,
  qa_notice_text: "",
  qa_notice_font_size: 16,
  qa_notice_color: "#111111",
  qa_notice_font_weight: 500,
  qa_notice_width: 420,
};

const NOTICE_TEXT_MAX = 200;
const QA_NOTICE_TEXT_MAX = 500;

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
        free_delay_notice_text: configQuery.data.free_delay_notice_text,
        pro_monthly_quota: configQuery.data.pro_monthly_quota,
        qa_notice_enabled: configQuery.data.qa_notice_enabled,
        qa_notice_text: configQuery.data.qa_notice_text,
        qa_notice_font_size: configQuery.data.qa_notice_font_size,
        qa_notice_color: configQuery.data.qa_notice_color,
        qa_notice_font_weight: configQuery.data.qa_notice_font_weight,
        qa_notice_width: configQuery.data.qa_notice_width,
      });
    }
  }, [configQuery.data]);

  const isDirty = configQuery.data
    ? form.show_subscribe_button !== configQuery.data.show_subscribe_button ||
      form.free_daily_quota !== configQuery.data.free_daily_quota ||
      form.free_delay_enabled !== configQuery.data.free_delay_enabled ||
      form.free_delay_seconds !== configQuery.data.free_delay_seconds ||
      form.free_delay_notice_text !== configQuery.data.free_delay_notice_text ||
      form.pro_monthly_quota !== configQuery.data.pro_monthly_quota ||
      form.qa_notice_enabled !== configQuery.data.qa_notice_enabled ||
      form.qa_notice_text !== configQuery.data.qa_notice_text ||
      form.qa_notice_font_size !== configQuery.data.qa_notice_font_size ||
      form.qa_notice_color !== configQuery.data.qa_notice_color ||
      form.qa_notice_font_weight !== configQuery.data.qa_notice_font_weight ||
      form.qa_notice_width !== configQuery.data.qa_notice_width
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
              value={form.free_daily_quota === 0 ? "" : form.free_daily_quota}
              placeholder="0"
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  free_daily_quota: e.target.value === "" ? 0 : Number(e.target.value),
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
            <span className={styles.rowLabel}>Pro 월 질문 가능 횟수</span>
            <span className={styles.rowDesc}>
              Pro 구독자가 한 달 동안 사용할 수 있는 질문 횟수입니다. 매월 1일 00시(KST) 초기화. (0~99999)
            </span>
          </div>
          <div className={styles.numberCell}>
            <input
              type="number"
              min={0}
              max={99999}
              step={1}
              className={styles.numberInput}
              value={form.pro_monthly_quota === 0 ? "" : form.pro_monthly_quota}
              placeholder="0"
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  pro_monthly_quota: e.target.value === "" ? 0 : Number(e.target.value),
                }))
              }
              aria-label="Pro 월 질문 가능 횟수"
            />
            <span className={styles.unit}>회</span>
          </div>
        </div>
        {errors.pro_monthly_quota ? (
          <p className={styles.fieldError} role="alert">
            {errors.pro_monthly_quota}
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
              value={form.free_delay_seconds === 0 ? "" : form.free_delay_seconds}
              placeholder="0"
              disabled={!form.free_delay_enabled}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  free_delay_seconds: e.target.value === "" ? 0 : Number(e.target.value),
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

        <div className={styles.row}>
          <div className={styles.rowText}>
            <span className={styles.rowLabel}>답변 지연 안내문구</span>
            <span className={styles.rowDesc}>
              위 토글이 ON일 때 사용자 채팅 입력창 위에 회색 글자로 노출됩니다. 비워두면 기본 문구로 표시됩니다.
            </span>
          </div>
        </div>
        <div className={styles.noticeTextCell}>
          <textarea
            className={styles.noticeTextarea}
            rows={2}
            maxLength={NOTICE_TEXT_MAX}
            placeholder="현재는 무료버전으로 답변 출력은 약 40초가량 소요됩니다."
            disabled={!form.free_delay_enabled}
            value={form.free_delay_notice_text}
            onChange={(e) =>
              setForm((p) => ({
                ...p,
                free_delay_notice_text: e.target.value,
              }))
            }
            aria-label="답변 지연 안내문구"
          />
          <span className={styles.noticeCount} aria-live="polite">
            {form.free_delay_notice_text.length} / {NOTICE_TEXT_MAX}
          </span>
        </div>
        {errors.free_delay_notice_text ? (
          <p className={styles.fieldError} role="alert">
            {errors.free_delay_notice_text}
          </p>
        ) : null}

        {/* #130 ① — 질문 전송 시 화면 중앙 안내 팝업 */}
        <div className={styles.row}>
          <div className={styles.rowText}>
            <span className={styles.rowLabel}>질문 전송 안내 팝업</span>
            <span className={styles.rowDesc}>
              로그인 사용자가 채팅에서 질문을 전송할 때마다 화면 정중앙에 안내 팝업을 띄웁니다. 사용자는 “확인” 또는 “오늘 하루 보지 않기”로 닫을 수 있습니다.
            </span>
          </div>
          <ToggleSwitch
            ariaLabel="질문 전송 안내 팝업 노출"
            checked={form.qa_notice_enabled}
            onChange={(v) =>
              setForm((p) => ({ ...p, qa_notice_enabled: v }))
            }
          />
        </div>

        <div className={styles.row}>
          <div className={styles.rowText}>
            <span className={styles.rowLabel}>안내 팝업 문구</span>
            <span className={styles.rowDesc}>
              팝업 본문에 표시됩니다. 비워두면 기본 문구로 표시됩니다.
            </span>
          </div>
        </div>
        <div className={styles.noticeTextCell}>
          <textarea
            className={styles.noticeTextarea}
            rows={3}
            maxLength={QA_NOTICE_TEXT_MAX}
            placeholder="현재 질문하신 내용에 대한 정보만 제공하며 이전에 질문하신 내용을 참고하여 정보를 제공하지 않습니다. Denvia는 매 질문을 항상 새로운 독립질문으로 처리합니다."
            disabled={!form.qa_notice_enabled}
            value={form.qa_notice_text}
            onChange={(e) =>
              setForm((p) => ({ ...p, qa_notice_text: e.target.value }))
            }
            aria-label="안내 팝업 문구"
          />
          <span className={styles.noticeCount} aria-live="polite">
            {form.qa_notice_text.length} / {QA_NOTICE_TEXT_MAX}
          </span>
        </div>
        {errors.qa_notice_text ? (
          <p className={styles.fieldError} role="alert">
            {errors.qa_notice_text}
          </p>
        ) : null}

        <div className={styles.row}>
          <div className={styles.rowText}>
            <span className={styles.rowLabel}>문구 글자 크기</span>
            <span className={styles.rowDesc}>
              팝업 본문 글자 크기(px)입니다. (10~40)
            </span>
          </div>
          <div className={styles.numberCell}>
            <input
              type="number"
              min={10}
              max={40}
              step={1}
              className={styles.numberInput}
              disabled={!form.qa_notice_enabled}
              value={form.qa_notice_font_size}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  qa_notice_font_size:
                    e.target.value === "" ? 0 : Number(e.target.value),
                }))
              }
              aria-label="문구 글자 크기 (px)"
            />
            <span className={styles.unit}>px</span>
          </div>
        </div>
        {errors.qa_notice_font_size ? (
          <p className={styles.fieldError} role="alert">
            {errors.qa_notice_font_size}
          </p>
        ) : null}

        <div className={styles.row}>
          <div className={styles.rowText}>
            <span className={styles.rowLabel}>문구 색상</span>
            <span className={styles.rowDesc}>
              팝업 본문 글자 색상입니다. 색상 상자를 눌러 선택하세요.
            </span>
          </div>
          <div className={styles.numberCell}>
            <input
              type="color"
              className={styles.colorInput}
              disabled={!form.qa_notice_enabled}
              value={
                /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(form.qa_notice_color)
                  ? form.qa_notice_color
                  : "#111111"
              }
              onChange={(e) =>
                setForm((p) => ({ ...p, qa_notice_color: e.target.value }))
              }
              aria-label="문구 색상 선택"
            />
            <input
              type="text"
              className={styles.colorTextInput}
              maxLength={7}
              placeholder="#111111"
              disabled={!form.qa_notice_enabled}
              value={form.qa_notice_color}
              onChange={(e) =>
                setForm((p) => ({ ...p, qa_notice_color: e.target.value }))
              }
              aria-label="문구 색상 hex 값"
            />
          </div>
        </div>
        {errors.qa_notice_color ? (
          <p className={styles.fieldError} role="alert">
            {errors.qa_notice_color}
          </p>
        ) : null}

        <div className={styles.row}>
          <div className={styles.rowText}>
            <span className={styles.rowLabel}>문구 두께</span>
            <span className={styles.rowDesc}>
              팝업 본문 글자 두께입니다. 400=보통, 700=굵게. (100~900)
            </span>
          </div>
          <div className={styles.numberCell}>
            <input
              type="number"
              min={100}
              max={900}
              step={100}
              className={styles.numberInput}
              disabled={!form.qa_notice_enabled}
              value={form.qa_notice_font_weight}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  qa_notice_font_weight:
                    e.target.value === "" ? 0 : Number(e.target.value),
                }))
              }
              aria-label="문구 두께"
            />
          </div>
        </div>
        {errors.qa_notice_font_weight ? (
          <p className={styles.fieldError} role="alert">
            {errors.qa_notice_font_weight}
          </p>
        ) : null}

        <div className={styles.row}>
          <div className={styles.rowText}>
            <span className={styles.rowLabel}>팝업 가로폭</span>
            <span className={styles.rowDesc}>
              팝업 상자의 가로폭(px)입니다. (280~720)
            </span>
          </div>
          <div className={styles.numberCell}>
            <input
              type="number"
              min={280}
              max={720}
              step={10}
              className={styles.numberInput}
              disabled={!form.qa_notice_enabled}
              value={form.qa_notice_width}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  qa_notice_width:
                    e.target.value === "" ? 0 : Number(e.target.value),
                }))
              }
              aria-label="팝업 가로폭 (px)"
            />
            <span className={styles.unit}>px</span>
          </div>
        </div>
        {errors.qa_notice_width ? (
          <p className={styles.fieldError} role="alert">
            {errors.qa_notice_width}
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
