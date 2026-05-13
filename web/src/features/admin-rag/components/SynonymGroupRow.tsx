"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ConfirmDialog } from "@/components/layout/ConfirmDialog";
import {
  deleteSynonymGroup,
  updateSynonymGroup,
  type SynonymGroup,
  type SynonymGroupInput,
} from "../api/synonyms";
import { SynonymGroupForm } from "./SynonymGroupForm";
import styles from "./SynonymGroupRow.module.css";

interface Props {
  group: SynonymGroup;
  occupiedTerms?: Map<string, { id: number; canonicalTerm: string }>;
}

export function SynonymGroupRow({ group, occupiedTerms }: Props) {
  const [editing, setEditing] = useState(false);
  const [confirmSave, setConfirmSave] = useState<SynonymGroupInput | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const qc = useQueryClient();

  const update = useMutation({
    mutationFn: (data: SynonymGroupInput) => updateSynonymGroup(group.id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-rag-synonyms"] });
      setEditing(false);
      setConfirmSave(null);
    },
  });

  const del = useMutation({
    mutationFn: () => deleteSynonymGroup(group.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-rag-synonyms"] });
      setConfirmDelete(false);
    },
  });

  if (editing) {
    return (
      <div className={styles.rowEditing}>
        <SynonymGroupForm
          initial={group}
          occupiedTerms={occupiedTerms}
          submitting={update.isPending}
          error={
            update.isError && update.error instanceof Error
              ? humanizeError(update.error.message)
              : null
          }
          onSubmit={(data) => setConfirmSave(data)}
          onCancel={() => setEditing(false)}
        />
        <ConfirmDialog
          open={confirmSave !== null}
          title="동의어 그룹 저장"
          description="이 변경은 약 1초 내 모든 신규 질문에 반영됩니다. 진행하시겠습니까?"
          confirmLabel="저장"
          onConfirm={() => confirmSave && update.mutate(confirmSave)}
          onCancel={() => setConfirmSave(null)}
        />
      </div>
    );
  }

  return (
    <div className={styles.row}>
      <div className={styles.canonicalCell}>
        <span className={styles.canonicalText}>{group.canonical_term}</span>
      </div>
      <div className={styles.synonymsCell}>
        {group.synonyms.length === 0 ? (
          <span className={styles.emptyText}>(없음)</span>
        ) : (
          group.synonyms.map((s) => (
            <span key={s} className={styles.chip}>
              {s}
            </span>
          ))
        )}
      </div>
      <div className={styles.actionsCell}>
        <button
          type="button"
          className={styles.editBtn}
          onClick={() => setEditing(true)}
        >
          편집
        </button>
        <button
          type="button"
          className={styles.deleteBtn}
          onClick={() => setConfirmDelete(true)}
        >
          삭제
        </button>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title="동의어 그룹 삭제"
        description="이 그룹을 삭제하면 해당 동의어들이 더 이상 표준어로 통일되지 않습니다. 진행하시겠습니까?"
        confirmLabel="삭제"
        danger
        onConfirm={() => del.mutate()}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  );
}

function humanizeError(code: string): string {
  switch (code) {
    case "SYNONYM_CONFLICT":
      return "이미 다른 그룹에서 사용 중인 표현이 있습니다.";
    case "SYNONYM_GROUP_NOT_FOUND":
      return "이미 삭제된 그룹입니다. 목록을 새로고침 해주세요.";
    default:
      return "저장에 실패했습니다.";
  }
}
