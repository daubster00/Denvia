"use client";

import { useEffect, useRef, useState } from "react";
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
  formatModelPrice,
  type ChatModelInfo,
} from "@/features/admin-dashboard/api/chatModel";
import {
  fetchChatHistoryConfig,
  updateChatHistoryConfig,
  type ChatHistoryConfig,
} from "@/features/admin-dashboard/api/chatHistory";
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

// 모델별 안내(이름·가격·속도·품질·주의)는 백엔드 카탈로그에서 내려온다.
// 프론트에 하드코딩하지 않는다 — 모델이 추가/종료되면 백엔드 표 한 곳만 고치면 된다.
function findModel(
  models: ChatModelInfo[],
  modelId: string,
): ChatModelInfo | undefined {
  return models.find((m) => m.model_id === modelId);
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

  const historyQuery = useQuery({
    queryKey: ["admin", "runtime-config", "chat-history"],
    queryFn: fetchChatHistoryConfig,
    // 3차 검수 P2 — 형제 쿼리와 같은 정책. 이 쿼리만 기본값(staleTime 0 +
    // 포커스 재조회 ON)이어서, 창 포커스로 시작된 재조회가 저장 성공 **뒤에**
    // 늦게 도착해 화면을 옛 값으로 되돌리는 경쟁이 있었다.
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

      <section
        id="chat-history"
        className={styles.card}
        aria-labelledby="chat-history-title"
      >
        <h2 id="chat-history-title" className={styles.cardTitle}>
          대화 이어가기
        </h2>
        <p className={styles.cardCaption}>
          앞선 대화를 참고해서 답변할지, 몇 턴까지 참고할지 정합니다. 질문 1건당 연관성
          판단을 위해 AI 호출이 1회 더 일어나므로 요금이 조금 늘어납니다. 변경 즉시 다음
          질문부터 적용됩니다.
        </p>

        {historyQuery.isLoading && (
          <p className={styles.statusMessage} role="status">
            대화 이어가기 설정을 불러오는 중…
          </p>
        )}

        {!historyQuery.isLoading && historyQuery.error && (
          <div className={styles.errorBox} role="alert">
            <p>대화 이어가기 설정을 불러오지 못했습니다.</p>
            <button
              type="button"
              className={styles.retryBtn}
              onClick={() => historyQuery.refetch()}
            >
              다시 시도
            </button>
          </div>
        )}

        {historyQuery.data && <ChatHistoryForm config={historyQuery.data} />}
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

  // 선택 중인 모델 / 현재 적용된 모델의 카탈로그 정보(가격·설명).
  const draftSpec = findModel(config.models, modelDraft);
  const currentSpec = findModel(config.models, config.chat_model);

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
          <dd>{currentSpec ? currentSpec.label : config.chat_model}</dd>
        </div>
        <div className={styles.summaryRow}>
          <dt>현재 요금</dt>
          <dd>{currentSpec ? formatModelPrice(currentSpec) : "—"}</dd>
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
          {config.models.map((m) => (
            <option key={m.model_id} value={m.model_id}>
              {m.label} — 출력 ${m.output_usd_per_mtok.toFixed(2)}/100만 토큰
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
        기본값은 {config.default_model} 입니다. 목록은 저렴한 모델부터 정렬돼 있으며,
        모델을 바꾸면 질문 1건당 사용 요금도 함께 바뀝니다. 변경 전 아래 안내를 확인하세요.
      </p>

      {draftSpec && (
        <dl className={styles.modelInfo}>
          <div className={styles.summaryRow}>
            <dt>사용 요금</dt>
            <dd>{formatModelPrice(draftSpec)}</dd>
          </div>
          <div className={styles.summaryRow}>
            <dt>등급</dt>
            <dd>{draftSpec.tier}</dd>
          </div>
          <div className={styles.summaryRow}>
            <dt>응답 속도</dt>
            <dd>{draftSpec.speed}</dd>
          </div>
          <div className={styles.summaryRow}>
            <dt>답변 특성</dt>
            <dd>{draftSpec.quality}</dd>
          </div>
          <div className={styles.summaryRow}>
            <dt>주의</dt>
            <dd>{draftSpec.note}</dd>
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


function ChatHistoryForm({ config }: { config: ChatHistoryConfig }) {
  const qc = useQueryClient();
  const [enabled, setEnabled] = useState(config.enabled);
  const [maxTurns, setMaxTurns] = useState(String(config.max_turns));
  const [maxTokens, setMaxTokens] = useState(String(config.max_tokens));
  const [model, setModel] = useState(config.rewriter_model);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  /**
   * 사용자가 이 폼의 입력을 **실제로 건드렸는가** (재수정 P1-3).
   *
   * 예전에는 "서버 값과 다르면 수정 중" (`dirty`) 으로 판정해 재조회 반영을 막았다.
   * 그 판정은 두 군데서 틀린다.
   *
   *   1. 다른 관리자가 값을 바꾸면, 내가 아무것도 건드리지 않았는데도 내 화면 값이
   *      새 서버 값과 달라진다 → `dirty=true` → **영원히 재초기화되지 않는다.**
   *      그 상태로 저장하면 상대의 변경을 옛 값으로 덮어쓴다.
   *   2. 내가 값을 바꿨다가 원래대로 되돌리면 `dirty=false` 가 되어, 입력 중인 폼이
   *      재조회 값으로 갑자기 바뀔 수 있다.
   *
   * 그래서 "서버 값과의 차이" 와 "사용자가 입력을 바꿨는가" 를 분리한다.
   * 재초기화 여부는 이 값만 본다. 저장 버튼 활성화는 서버 값과의 차이(`dirty`)를 본다.
   */
  const [hasLocalEdits, setHasLocalEdits] = useState(false);

  const mutation = useMutation({
    mutationFn: updateChatHistoryConfig,
    onSuccess: (updated: ChatHistoryConfig) => {
      qc.setQueryData(["admin", "runtime-config", "chat-history"], updated);
      setEnabled(updated.enabled);
      setMaxTurns(String(updated.max_turns));
      setMaxTokens(String(updated.max_tokens));
      setModel(updated.rewriter_model);
      // 저장 성공 = 내 편집이 서버에 반영됐다 → 편집 중 상태를 해제한다.
      // 해제하지 않으면 이후 다른 관리자의 변경이 영원히 화면에 반영되지 않는다.
      setHasLocalEdits(false);
      setSavedMessage("대화 이어가기 설정이 저장되었습니다.");
      window.setTimeout(() => setSavedMessage(null), 2500);
    },
  });

  const turnsNum = Number(maxTurns);
  const tokensNum = Number(maxTokens);
  // 3차 검수 P2 — "사용 안 함" 으로 끄면 턴·토큰 입력란이 비활성화되는데, 그 전에
  // 입력란을 비워 뒀으면 **저장도 수정도 못 하는 막힌 상태**가 됐다
  // (저장 버튼은 값이 유효하지 않아 비활성, 입력란은 꺼져 있어 비활성).
  // 꺼진 상태에서는 그 값들이 의미가 없으므로 검증을 건너뛰고 저장을 허용한다.
  const numbersMatter = enabled;
  const turnsValid =
    !numbersMatter ||
    (Number.isInteger(turnsNum) && turnsNum >= 1 && turnsNum <= 20);
  const tokensValid =
    !numbersMatter ||
    (Number.isInteger(tokensNum) && tokensNum >= 500 && tokensNum <= 20000);
  const dirty =
    enabled !== config.enabled ||
    turnsNum !== config.max_turns ||
    tokensNum !== config.max_tokens ||
    model !== config.rewriter_model;

  // 검수 P1-9 / 재수정 P1-3 — 다른 관리자가 값을 바꿔 재조회되면 화면 입력도 따라와야
  // 한다. 그대로 두면 이 화면의 옛 값으로 다음 저장이 상대 변경을 덮어쓴다.
  // 단, **사용자가 실제로 입력을 바꾼 폼은 건드리지 않는다** — 입력하던 값이 사라지면
  // 안 된다. 판정은 `dirty`(서버 값과의 차이)가 아니라 `hasLocalEdits`(실제 입력 변경)로
  // 한다. `dirty` 로 판정하면 상대가 값을 바꾼 순간 내 화면이 영구히 고정됐다.
  const hasLocalEditsRef = useRef(hasLocalEdits);
  hasLocalEditsRef.current = hasLocalEdits;
  useEffect(() => {
    if (hasLocalEditsRef.current) return;
    setEnabled(config.enabled);
    setMaxTurns(String(config.max_turns));
    setMaxTokens(String(config.max_tokens));
    setModel(config.rewriter_model);
  }, [config.enabled, config.max_turns, config.max_tokens, config.rewriter_model]);

  return (
    <form
      className={styles.form}
      onSubmit={(e) => {
        e.preventDefault();
        setSavedMessage(null);
        if (!turnsValid || !tokensValid) return;
        mutation.mutate({
          enabled,
          // 꺼진 상태에서 입력란을 비워 뒀을 수 있다 → 그때는 서버 현재값을 그대로 보낸다
          // (0 같은 값이 저장되면 다시 켤 때 범위 밖 값이 들어간다).
          max_turns: Number.isInteger(turnsNum) && turnsNum >= 1
            ? turnsNum
            : config.max_turns,
          max_tokens: Number.isInteger(tokensNum) && tokensNum >= 500
            ? tokensNum
            : config.max_tokens,
          rewriter_model: model,
        });
      }}
      noValidate
    >
      <dl className={styles.summary}>
        <div className={styles.summaryRow}>
          <dt>현재 상태</dt>
          <dd>{config.enabled ? "사용 중" : "사용 안 함"}</dd>
        </div>
        <div className={styles.summaryRow}>
          <dt>기본값</dt>
          <dd>
            최근 {config.default_max_turns}턴 / {config.default_max_tokens.toLocaleString()}토큰
          </dd>
        </div>
      </dl>

      <label className={styles.fieldLabel} htmlFor="chat-history-enabled">
        <input
          id="chat-history-enabled"
          type="checkbox"
          checked={enabled}
          onChange={(e) => {
            setHasLocalEdits(true);
            setEnabled(e.target.checked);
          }}
        />{" "}
        앞선 대화를 참고해서 답변하기
      </label>
      <p className={styles.fieldHint}>
        끄면 예전처럼 질문 1개에 답변 1개만 합니다(연관성 판단 호출도 하지 않습니다).
      </p>

      <label className={styles.fieldLabel} htmlFor="chat-history-turns">
        참고할 최근 대화 수 (1~20턴)
      </label>
      <input
        id="chat-history-turns"
        type="number"
        min={1}
        max={20}
        className={styles.select}
        value={maxTurns}
        onChange={(e) => {
          setHasLocalEdits(true);
          setMaxTurns(e.target.value);
        }}
        disabled={!enabled}
      />
      <p className={styles.fieldHint}>
        질문 1개와 그 답변 1개가 1턴입니다.
      </p>

      <label className={styles.fieldLabel} htmlFor="chat-history-tokens">
        이전 대화 분량 상한 (500~20,000토큰)
      </label>
      <input
        id="chat-history-tokens"
        type="number"
        min={500}
        max={20000}
        step={100}
        className={styles.select}
        value={maxTokens}
        onChange={(e) => {
          setHasLocalEdits(true);
          setMaxTokens(e.target.value);
        }}
        disabled={!enabled}
      />
      <p className={styles.fieldHint}>
        이 분량을 넘으면 오래된 대화부터 뺍니다. 가장 최근 1턴은 길이와 상관없이 항상
        유지합니다. 이 상한에는 이전 질문·답변만 포함되고 참고자료와 이번 질문은 빠집니다.
      </p>

      <label className={styles.fieldLabel} htmlFor="chat-history-model">
        연관성 판단에 쓸 모델
      </label>
      <select
        id="chat-history-model"
        className={styles.select}
        value={model}
        onChange={(e) => {
          setHasLocalEdits(true);
          setModel(e.target.value);
        }}
        disabled={!enabled}
      >
        {config.models.map((m) => (
          <option key={m.model_id} value={m.model_id}>
            {m.label} — 출력 ${m.output_usd_per_mtok.toFixed(2)}/100만 토큰
          </option>
        ))}
      </select>
      <p className={styles.fieldHint}>
        &quot;이 질문이 앞 대화에 이어지는가&quot;만 판단하는 짧은 작업이라 가장 저렴한
        모델로 충분합니다.
      </p>

      <div className={styles.fieldRow}>
        <button
          type="submit"
          className={styles.saveBtn}
          disabled={mutation.isPending || !dirty || !turnsValid || !tokensValid}
        >
          {mutation.isPending ? "저장 중…" : "저장"}
        </button>
      </div>

      {enabled && (!turnsValid || !tokensValid) && (
        <p className={styles.errorText} role="alert">
          {!turnsValid
            ? "참고할 대화 수는 1~20 사이의 정수여야 합니다."
            : "이전 대화 분량 상한은 500~20,000 사이의 정수여야 합니다."}
        </p>
      )}

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
  );
}
