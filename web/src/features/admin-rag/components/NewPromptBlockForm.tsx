"use client";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ConfirmDialog } from "@/components/layout/ConfirmDialog";
import {
  createPromptBlock,
  type PromptCreatePayload,
  type TriggerConfig,
} from "../api/prompts";
import {
  cleanTrigger,
  ERROR_MESSAGES,
  SuppressEditor,
  triggerValid,
  TriggerEditor,
} from "./promptTrigger";
import styles from "./PromptBlockCard.module.css";

const EMPTY_TRIGGER: TriggerConfig = { mode: "keywords", keywords: [] };

interface Props {
  /** 예외처리 대상 선택용 — 전체 블록 id 목록. */
  allBlockIds: string[];
}

export function NewPromptBlockForm({ allBlockIds }: Props) {
  const [open, setOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [trigger, setTrigger] = useState<TriggerConfig>(EMPTY_TRIGGER);
  const [suppresses, setSuppresses] = useState<string[]>([]);
  const queryClient = useQueryClient();

  const reset = () => {
    setName("");
    setContent("");
    setEnabled(true);
    setTrigger(EMPTY_TRIGGER);
    setSuppresses([]);
  };

  const mutation = useMutation({
    mutationFn: (data: PromptCreatePayload) => createPromptBlock(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-rag-prompts"] });
      setConfirmOpen(false);
      reset();
      setOpen(false);
    },
  });

  const nameOk = name.trim().length > 0;
  const contentOk = content.trim().length > 0;
  const canSubmit = nameOk && contentOk && triggerValid(trigger) && !mutation.isPending;

  const submit = () => {
    setConfirmOpen(true);
  };

  const handleConfirm = () => {
    mutation.mutate({
      block_id: name.trim(),
      content,
      enabled,
      trigger_config: cleanTrigger(trigger),
      suppresses,
    });
  };

  const errorMsg =
    mutation.isError && mutation.error instanceof Error
      ? ERROR_MESSAGES[mutation.error.message] ?? "생성 실패"
      : null;

  return (
    <div className={styles.newCard}>
      <button type="button" className={styles.newToggle} onClick={() => setOpen((o) => !o)}>
        <span>＋ 새 블록 만들기</span>
        <span className={styles.chevron}>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className={styles.body}>
          <div className={styles.nameRow}>
            <div className={styles.triggerLabel}>블록 이름</div>
            <div className={styles.triggerHint}>
              규칙을 알아볼 수 있는 이름을 지어주세요. (예: 파노라마_산정) — 만든 뒤에는 이름이 고정됩니다.
            </div>
            <input
              type="text"
              className={styles.nameInput}
              value={name}
              maxLength={40}
              placeholder="블록 이름"
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className={styles.triggerSection}>
            <div className={styles.triggerHeading}>발동 조건</div>
            <TriggerEditor trigger={trigger} setTrigger={setTrigger} />
          </div>

          <div className={styles.triggerSection}>
            <div className={styles.triggerHeading}>예외처리 (상호배제)</div>
            <SuppressEditor
              allBlockIds={allBlockIds}
              selfId={null}
              value={suppresses}
              onChange={setSuppresses}
            />
          </div>

          <label className={styles.enabledLabel}>
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            <span>블록 활성화</span>
          </label>

          <div className={styles.triggerHeading}>블록 내용</div>
          <textarea
            className={styles.textarea}
            rows={10}
            value={content}
            placeholder="이 규칙이 켜졌을 때 챗봇에게 줄 지시 내용을 적어주세요."
            onChange={(e) => setContent(e.target.value)}
          />

          {errorMsg && <p className={styles.error}>{errorMsg}</p>}

          <div className={styles.actions}>
            <button
              type="button"
              className={styles.cancelBtn}
              onClick={() => {
                reset();
                setOpen(false);
              }}
            >
              취소
            </button>
            <button
              type="button"
              className={styles.saveBtn}
              onClick={submit}
              disabled={!canSubmit}
            >
              {mutation.isPending ? "만드는 중..." : "블록 만들기"}
            </button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmOpen}
        title="블록 만들기"
        description="새 블록이 모든 신규 답변에 즉시 반영됩니다. 진행하시겠습니까?"
        confirmLabel="만들기"
        onConfirm={handleConfirm}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
