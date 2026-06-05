"use client";

/**
 * 관리자 설정 → 결제(PG) 페이지.
 *
 * 토스 PG 모드(테스트 ↔ 실결제) 토글 + 4개 키 편집.
 * - 키 값은 항상 마스킹되어 표시되며, "수정" 클릭 시 빈 입력창이 열린다.
 * - 빈 채로 저장하면 해당 키는 변경되지 않는다 (부분 업데이트).
 * - 모드 토글은 즉시 저장되어 다음 결제 호출부터 반영된다.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchTossPgConfig,
  updateTossPgConfig,
  type TossMode,
  type TossPgConfig,
  type TossPgConfigUpdatePayload,
  type TossPgKeyView,
} from "@/features/admin-dashboard/api/tossPg";
import styles from "./page.module.css";

type KeyField =
  | "test_client_key"
  | "test_secret_key"
  | "live_client_key"
  | "live_secret_key";

interface KeyMeta {
  field: KeyField;
  label: string;
  description: string;
  mode: TossMode;
  isSecret: boolean;
}

const KEY_META: KeyMeta[] = [
  {
    field: "test_client_key",
    label: "테스트 클라이언트 키",
    description: "결제창 초기화 시 브라우저로 전달되는 공개 키 (test_ck_…).",
    mode: "test",
    isSecret: false,
  },
  {
    field: "test_secret_key",
    label: "테스트 시크릿 키",
    description: "서버에서 토스 API 호출 시 사용 (test_sk_…). 외부 노출 금지.",
    mode: "test",
    isSecret: true,
  },
  {
    field: "live_client_key",
    label: "실결제 클라이언트 키",
    description: "심사 통과 후 실 카드 결제용 공개 키 (live_ck_…).",
    mode: "live",
    isSecret: false,
  },
  {
    field: "live_secret_key",
    label: "실결제 시크릿 키",
    description: "심사 통과 후 실 카드 결제용 시크릿 (live_sk_…). 절대 외부 노출 금지.",
    mode: "live",
    isSecret: true,
  },
];

function getKeyView(config: TossPgConfig, field: KeyField): TossPgKeyView {
  switch (field) {
    case "test_client_key":
      return config.test_client;
    case "test_secret_key":
      return config.test_secret;
    case "live_client_key":
      return config.live_client;
    case "live_secret_key":
      return config.live_secret;
  }
}

export default function PaymentSettingsPage() {
  const qc = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["admin", "runtime-config", "toss-pg"],
    queryFn: fetchTossPgConfig,
    refetchOnWindowFocus: false,
  });

  const [editingField, setEditingField] = useState<KeyField | null>(null);
  const [draftValue, setDraftValue] = useState<string>("");
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (payload: TossPgConfigUpdatePayload) => updateTossPgConfig(payload),
    onSuccess: (updated, variables) => {
      qc.setQueryData(["admin", "runtime-config", "toss-pg"], updated);
      if (variables.mode) {
        setSavedMessage(
          variables.mode === "live"
            ? "실결제 모드로 전환되었습니다."
            : "테스트 모드로 전환되었습니다.",
        );
      } else {
        setSavedMessage("저장되었습니다.");
      }
      setEditingField(null);
      setDraftValue("");
      window.setTimeout(() => setSavedMessage(null), 3000);
    },
  });

  const handleModeChange = (next: TossMode) => {
    if (!data || data.mode === next || mutation.isPending) return;
    // 실결제 모드로 전환 전에 한 번 더 확인 — 실 결제 키 누락 시 결제 실패할 수 있음
    if (next === "live") {
      const hasLiveKeys =
        data.live_client.has_value && data.live_secret.has_value;
      if (!hasLiveKeys) {
        const confirmed = window.confirm(
          "실결제 키가 비어있습니다. 그래도 실결제 모드로 전환하시겠습니까?\n전환 후 키를 채우지 않으면 모든 결제 요청이 실패합니다.",
        );
        if (!confirmed) return;
      } else {
        const confirmed = window.confirm(
          "실결제 모드로 전환합니다. 다음 결제 요청부터 실 카드로 청구됩니다.\n계속하시겠습니까?",
        );
        if (!confirmed) return;
      }
    }
    setSavedMessage(null);
    mutation.mutate({ mode: next });
  };

  const handleStartEdit = (field: KeyField) => {
    setEditingField(field);
    setDraftValue("");
    setSavedMessage(null);
  };

  const handleCancelEdit = () => {
    setEditingField(null);
    setDraftValue("");
  };

  const handleSaveKey = (field: KeyField) => {
    const value = draftValue.trim();
    if (!value) return;
    setSavedMessage(null);
    mutation.mutate({ [field]: value } as TossPgConfigUpdatePayload);
  };

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>결제(PG) 키 관리</h1>
        <p className={styles.caption}>
          토스페이먼츠의 테스트 모드와 실결제 모드를 전환하고, 각 모드의 클라이언트
          키·시크릿 키를 관리합니다. 키 값은 일부만 노출되며, 수정 버튼을 눌러야
          새 값을 입력할 수 있습니다.
        </p>
      </header>

      {isLoading && (
        <p className={styles.statusMessage} role="status">
          결제 설정을 불러오는 중…
        </p>
      )}

      {!isLoading && error && (
        <div className={styles.errorBox} role="alert">
          <p>결제 설정을 불러오지 못했습니다.</p>
          <button
            type="button"
            className={styles.retryBtn}
            onClick={() => refetch()}
          >
            다시 시도
          </button>
        </div>
      )}

      {data && (
        <>
          <section className={styles.card} aria-labelledby="pg-mode-title">
            <h2 id="pg-mode-title" className={styles.cardTitle}>
              현재 모드
            </h2>
            <p className={styles.cardCaption}>
              테스트 모드에서는 실제 카드 청구가 일어나지 않습니다. 토스 심사가 끝나면
              실결제 모드로 전환하세요. 전환은 즉시 반영됩니다.
            </p>

            <div className={styles.modeRow}>
              <button
                type="button"
                className={`${styles.modeBtn} ${data.mode === "test" ? styles.modeBtnActive : ""}`}
                onClick={() => handleModeChange("test")}
                disabled={mutation.isPending}
                aria-pressed={data.mode === "test"}
              >
                테스트 모드
              </button>
              <button
                type="button"
                className={`${styles.modeBtn} ${styles.modeBtnLive} ${data.mode === "live" ? styles.modeBtnActive : ""}`}
                onClick={() => handleModeChange("live")}
                disabled={mutation.isPending}
                aria-pressed={data.mode === "live"}
              >
                실결제 모드
              </button>
              <span
                className={`${styles.modeStatus} ${data.mode === "live" ? styles.modeStatusLive : ""}`}
              >
                현재: {data.mode === "live" ? "실결제 모드 (실 카드 청구됨)" : "테스트 모드 (실 청구 없음)"}
              </span>
            </div>

            {data.mode === "live" && (
              <div className={styles.warningBox} role="status">
                실결제 모드입니다. 결제 요청 시 실제 카드에 청구됩니다.
                키를 잘못 입력하면 모든 결제가 실패하니 주의하세요.
              </div>
            )}

            {savedMessage && (
              <p className={styles.successText} role="status">
                {savedMessage}
              </p>
            )}

            {mutation.isError && (
              <p className={styles.errorText} role="alert">
                {(mutation.error as Error)?.message ?? "저장에 실패했습니다."}
              </p>
            )}
          </section>

          <section className={styles.card} aria-labelledby="pg-keys-title">
            <h2 id="pg-keys-title" className={styles.cardTitle}>
              키 관리
            </h2>
            <p className={styles.cardCaption}>
              값이 일부만 보이는 것은 정상입니다. 새 값을 넣고 싶으면 "수정" 버튼을
              누르세요. 수정 화면을 비운 채 저장하면 기존 값은 그대로 유지됩니다.
            </p>

            <div className={styles.keysGrid}>
              {KEY_META.map((meta) => {
                const view = getKeyView(data, meta.field);
                const isEditing = editingField === meta.field;
                const isActiveMode = data.mode === meta.mode;
                const cardClass = isActiveMode
                  ? meta.mode === "live"
                    ? `${styles.keyCard} ${styles.keyCardActiveLive}`
                    : `${styles.keyCard} ${styles.keyCardActive}`
                  : styles.keyCard;
                const tagClass =
                  meta.mode === "live"
                    ? `${styles.keyTag} ${styles.keyTagLive}`
                    : styles.keyTag;

                return (
                  <article key={meta.field} className={cardClass}>
                    <header className={styles.keyHeader}>
                      <span className={styles.keyLabel}>{meta.label}</span>
                      <span className={tagClass}>
                        {meta.mode === "live" ? "실결제" : "테스트"}
                        {isActiveMode ? " · 활성" : ""}
                      </span>
                    </header>

                    <p className={styles.fieldHint}>{meta.description}</p>

                    {!isEditing && (
                      <div className={styles.keyValue}>
                        {view.has_value ? (
                          <span>{view.masked}</span>
                        ) : (
                          <span className={styles.keyValueEmpty}>(미설정)</span>
                        )}
                        <button
                          type="button"
                          className={styles.editBtn}
                          onClick={() => handleStartEdit(meta.field)}
                        >
                          수정
                        </button>
                      </div>
                    )}

                    {isEditing && (
                      <form
                        className={styles.editForm}
                        onSubmit={(e) => {
                          e.preventDefault();
                          handleSaveKey(meta.field);
                        }}
                      >
                        <input
                          type={meta.isSecret ? "password" : "text"}
                          className={styles.input}
                          value={draftValue}
                          onChange={(e) => setDraftValue(e.target.value)}
                          placeholder={
                            meta.mode === "test"
                              ? meta.isSecret
                                ? "test_sk_..."
                                : "test_ck_..."
                              : meta.isSecret
                              ? "live_sk_..."
                              : "live_ck_..."
                          }
                          autoFocus
                          autoComplete="off"
                          spellCheck={false}
                        />
                        <p className={styles.fieldHint}>
                          입력한 값으로 즉시 교체됩니다. 비운 채 저장하면 변경되지 않습니다.
                        </p>
                        <div className={styles.editActions}>
                          <button
                            type="submit"
                            className={styles.saveBtn}
                            disabled={
                              mutation.isPending || draftValue.trim().length === 0
                            }
                          >
                            {mutation.isPending ? "저장 중…" : "저장"}
                          </button>
                          <button
                            type="button"
                            className={styles.cancelBtn}
                            onClick={handleCancelEdit}
                            disabled={mutation.isPending}
                          >
                            취소
                          </button>
                        </div>
                      </form>
                    )}
                  </article>
                );
              })}
            </div>
          </section>
        </>
      )}
    </section>
  );
}
