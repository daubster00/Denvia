"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchBudgetCurrentMonth,
  updateMonthlyBudgetLimit,
  type BudgetCurrentMonth,
} from "@/features/admin-dashboard/api/budget";
import {
  fetchChatModelConfig,
  updateChatModelConfig,
  type ChatModelConfig,
} from "@/features/admin-dashboard/api/chatModel";
import {
  fetchForexConfig,
  type ForexConfig,
} from "@/features/admin-dashboard/api/forex";
import { formatKRW, usdToKrwInt } from "@/lib/format-currency";
import styles from "./page.module.css";

// "2026-05-21T08:00:12.345Z" → "2026-05-21 17:00 KST" (사용자 친화)
function formatKstFromIso(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  const fmt = new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return `${fmt.format(d).replace(/\. /g, "-").replace(/\./g, "")} KST`;
}

// 모델별 사용자 안내 카피 — 응답 속도/품질/비용 특성을 비전문가에게 설명.
const MODEL_DESCRIPTIONS: Record<string, { title: string; speed: string; quality: string; note: string }> = {
  "o4-mini": {
    title: "o4-mini (기본값)",
    speed: "느림 (첫 글자까지 5~20초)",
    quality: "추론 강함 · 인수자가 튜닝한 기본 모델",
    note: "타이핑 애니메이션이 거의 보이지 않습니다. 답변이 한꺼번에 떨어집니다.",
  },
  "gpt-4o-mini": {
    title: "gpt-4o-mini (가장 빠름 · 가장 저렴)",
    speed: "매우 빠름 (첫 글자까지 0.5~1초)",
    quality: "일반 대화 · 단순 질의 우수",
    note: "타이핑 애니메이션이 부드럽게 보입니다. 응답 체감이 가장 빠른 옵션입니다.",
  },
  "gpt-4o": {
    title: "gpt-4o (빠르고 똑똑)",
    speed: "빠름 (첫 글자까지 1~2초)",
    quality: "최고 품질의 일반 답변",
    note: "속도와 품질 균형이 가장 좋습니다. 가격은 mini보다 비쌉니다.",
  },
  "gpt-4-turbo": {
    title: "gpt-4-turbo (가장 똑똑)",
    speed: "보통 (첫 글자까지 2~3초)",
    quality: "매우 똑똑 · 긴 추론 가능",
    note: "정확성을 최우선으로 할 때 사용. 가격이 가장 비쌉니다.",
  },
};

function getModelDescription(model: string) {
  return (
    MODEL_DESCRIPTIONS[model] ?? {
      title: model,
      speed: "—",
      quality: "—",
      note: "이 모델의 상세 안내는 준비되지 않았습니다.",
    }
  );
}

export default function SettingsPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["admin", "budget", "current"],
    // queryFn에 함수를 직접 넘기면 React Query가 context를 자동 주입함 — 래핑 필수.
    queryFn: () => fetchBudgetCurrentMonth(),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const modelQuery = useQuery({
    queryKey: ["admin", "runtime-config", "chat-model"],
    queryFn: fetchChatModelConfig,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const forexQuery = useQuery({
    queryKey: ["admin", "runtime-config", "forex"],
    queryFn: fetchForexConfig,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>관리자 설정</h1>
        <p className={styles.caption}>
          이번 달에 사용할 수 있는 토큰 예산 한도를 조정합니다. 변경 즉시
          반영되며, 80% · 95% · 100% 자동 경고는 새로운 한도를 기준으로 다시
          판정됩니다.
        </p>
      </header>

      {isLoading && (
        <p className={styles.statusMessage} role="status">
          현재 한도를 불러오는 중…
        </p>
      )}

      {!isLoading && error && (
        <section className={styles.errorBox} role="alert">
          <p>예산 정보를 불러오지 못했습니다.</p>
          <button
            type="button"
            className={styles.retryBtn}
            onClick={() => refetch()}
          >
            다시 시도
          </button>
        </section>
      )}

      {data && <BudgetForm budget={data} forex={forexQuery.data ?? null} />}

      <section
        id="chat-model"
        className={styles.card}
        aria-labelledby="chat-model-title"
      >
        <h2 id="chat-model-title" className={styles.cardTitle}>
          AI 모델 선택
        </h2>
        <p className={styles.cardCaption}>
          챗봇이 답변을 만들 때 사용할 GPT 모델을 고릅니다. 답변 속도·품질·요금이
          달라집니다. 변경 즉시 다음 질문부터 적용됩니다.
        </p>

        {modelQuery.isLoading && (
          <p className={styles.statusMessage} role="status">
            현재 모델 정보를 불러오는 중…
          </p>
        )}

        {!modelQuery.isLoading && modelQuery.error && (
          <div className={styles.errorBox} role="alert">
            <p>AI 모델 설정을 불러오지 못했습니다.</p>
            <button
              type="button"
              className={styles.retryBtn}
              onClick={() => modelQuery.refetch()}
            >
              다시 시도
            </button>
          </div>
        )}

        {modelQuery.data && <ModelForm config={modelQuery.data} />}
      </section>
    </section>
  );
}

function BudgetForm({
  budget,
  forex,
}: {
  budget: BudgetCurrentMonth;
  forex: ForexConfig | null;
}) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<string>(
    Number(budget.monthly_limit_usd).toFixed(2),
  );
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (value: number) => updateMonthlyBudgetLimit(value),
    onSuccess: (updated) => {
      qc.setQueryData(["admin", "budget", "current"], updated);
      qc.invalidateQueries({ queryKey: ["admin", "budget"] });
      setDraft(Number(updated.monthly_limit_usd).toFixed(2));
      setSavedMessage("저장되었습니다.");
      window.setTimeout(() => setSavedMessage(null), 2500);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSavedMessage(null);
    const parsed = Number(draft);
    if (!Number.isFinite(parsed) || parsed <= 0 || parsed > 999_999.99) {
      return;
    }
    mutation.mutate(Number(parsed.toFixed(2)));
  };

  const currentLimit = Number(budget.monthly_limit_usd);
  const usdToKrw = budget.usd_to_krw ?? 1400;
  const currentLimitKrw = budget.monthly_limit_krw ?? 0;
  const spentKrw = budget.spent_krw ?? 0;
  const percent = budget.percent ?? 0;
  const draftNumber = Number(draft);
  const draftKrwPreview =
    Number.isFinite(draftNumber) && draftNumber > 0
      ? usdToKrwInt(draftNumber, usdToKrw)
      : 0;
  const isDraftValid =
    Number.isFinite(draftNumber) && draftNumber > 0 && draftNumber <= 999_999.99;
  const isDirty =
    isDraftValid &&
    Number(draftNumber.toFixed(2)) !== Number(currentLimit.toFixed(2));

  return (
    <section
      id="monthly-budget"
      className={styles.card}
      aria-labelledby="monthly-budget-title"
    >
      <h2 id="monthly-budget-title" className={styles.cardTitle}>
        월 예산 한도
      </h2>

      <dl className={styles.summary}>
        <div className={styles.summaryRow}>
          <dt>대상 월</dt>
          <dd>{budget.year_month}</dd>
        </div>
        <div className={styles.summaryRow}>
          <dt>현재 한도</dt>
          <dd>
            {formatKRW(currentLimitKrw)}{" "}
            <span className={styles.unitNote}>
              (USD ${currentLimit.toFixed(2)} · 환율 ₩{usdToKrw.toLocaleString("ko-KR")}/$)
            </span>
            <div className={styles.forexMeta}>
              {forex?.source === "auto" ? (
                <span className={styles.forexMetaTag}>자동 갱신</span>
              ) : (
                <span
                  className={`${styles.forexMetaTag} ${styles.forexMetaTagFallback}`}
                >
                  기본값 사용 중
                </span>
              )}
              <span>
                한국수출입은행 매일 09:00 KST 자동 반영
                {forex?.updated_at
                  ? ` · 최근 갱신 ${formatKstFromIso(forex.updated_at)}`
                  : ""}
                {forex?.search_date
                  ? ` · 기준 영업일 ${forex.search_date}`
                  : ""}
              </span>
            </div>
          </dd>
        </div>
        <div className={styles.summaryRow}>
          <dt>이미 사용한 금액</dt>
          <dd>
            {formatKRW(spentKrw)} ({percent.toFixed(1)}%)
          </dd>
        </div>
      </dl>

      <form className={styles.form} onSubmit={handleSubmit} noValidate>
        <label className={styles.fieldLabel} htmlFor="monthly-limit-input">
          새 한도 (USD 기준)
        </label>
        <div className={styles.fieldRow}>
          <span className={styles.unitPrefix} aria-hidden="true">
            $
          </span>
          <input
            id="monthly-limit-input"
            type="number"
            min="0.01"
            step="0.01"
            max="999999.99"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className={styles.input}
            aria-describedby="monthly-limit-help"
            required
          />
          <button
            type="submit"
            className={styles.saveBtn}
            disabled={mutation.isPending || !isDraftValid || !isDirty}
          >
            {mutation.isPending ? "저장 중…" : "저장"}
          </button>
        </div>
        <p id="monthly-limit-help" className={styles.fieldHint}>
          0.01 이상 999,999.99 이하의 USD 금액을 입력하세요. OpenAI 청구가 USD라 입력 단위는 달러로 유지합니다.
          {isDraftValid && draftKrwPreview > 0 ? (
            <>
              {" "}예상 한도: <strong>{formatKRW(draftKrwPreview)}</strong> (환율 ₩
              {usdToKrw.toLocaleString("ko-KR")}/$ 적용)
            </>
          ) : null}
        </p>

        {mutation.isError && (
          <p className={styles.errorText} role="alert">
            {(mutation.error as Error)?.message ?? "저장에 실패했습니다."}
          </p>
        )}

        {savedMessage && (
          <p className={styles.successText} role="status">
            {savedMessage}
          </p>
        )}
      </form>
    </section>
  );
}

function ModelForm({ config }: { config: ChatModelConfig }) {
  const qc = useQueryClient();
  const [modelDraft, setModelDraft] = useState<string>(config.chat_model);
  const [modelSavedMessage, setModelSavedMessage] = useState<string | null>(null);

  const modelMutation = useMutation({
    mutationFn: (value: string) => updateChatModelConfig(value),
    onSuccess: (updated: ChatModelConfig) => {
      qc.setQueryData(["admin", "runtime-config", "chat-model"], updated);
      setModelDraft(updated.chat_model);
      setModelSavedMessage("AI 모델이 변경되었습니다.");
      window.setTimeout(() => setModelSavedMessage(null), 2500);
    },
  });

  return (
    <form
      className={styles.form}
      onSubmit={(e) => {
        e.preventDefault();
        setModelSavedMessage(null);
        if (
          !modelDraft ||
          modelDraft === config.chat_model ||
          !config.allowed_models.includes(modelDraft)
        ) {
          return;
        }
        modelMutation.mutate(modelDraft);
      }}
      noValidate
    >
      <dl className={styles.summary}>
        <div className={styles.summaryRow}>
          <dt>현재 모델</dt>
          <dd>{config.chat_model}</dd>
        </div>
        <div className={styles.summaryRow}>
          <dt>기본값</dt>
          <dd>{config.default_model}</dd>
        </div>
      </dl>

      <label className={styles.fieldLabel} htmlFor="chat-model-select">
        사용할 모델
      </label>
      <div className={styles.fieldRow}>
        <select
          id="chat-model-select"
          className={styles.select}
          value={modelDraft}
          onChange={(e) => setModelDraft(e.target.value)}
          aria-describedby="chat-model-help"
        >
          {config.allowed_models.map((m) => (
            <option key={m} value={m}>
              {getModelDescription(m).title}
            </option>
          ))}
        </select>
        <button
          type="submit"
          className={styles.saveBtn}
          disabled={
            modelMutation.isPending ||
            !modelDraft ||
            modelDraft === config.chat_model
          }
        >
          {modelMutation.isPending ? "저장 중…" : "저장"}
        </button>
      </div>
      <p id="chat-model-help" className={styles.fieldHint}>
        인수자가 튜닝한 기본값은 {config.default_model} 입니다.
        변경 전 아래 안내를 확인하세요.
      </p>

      {modelDraft && (
        <dl className={styles.modelInfo}>
          <div className={styles.summaryRow}>
            <dt>응답 속도</dt>
            <dd>{getModelDescription(modelDraft).speed}</dd>
          </div>
          <div className={styles.summaryRow}>
            <dt>답변 특성</dt>
            <dd>{getModelDescription(modelDraft).quality}</dd>
          </div>
          <div className={styles.summaryRow}>
            <dt>주의</dt>
            <dd>{getModelDescription(modelDraft).note}</dd>
          </div>
        </dl>
      )}

      {modelMutation.isError && (
        <p className={styles.errorText} role="alert">
          {(modelMutation.error as Error)?.message ??
            "AI 모델 변경에 실패했습니다."}
        </p>
      )}

      {modelSavedMessage && (
        <p className={styles.successText} role="status">
          {modelSavedMessage}
        </p>
      )}
    </form>
  );
}
