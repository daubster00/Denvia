"use client";

/**
 * 수정요청 게시판 첨부 파일 선택기.
 *
 * 문서/압축/이미지, 파일당 20MB, 글당 최대 10개.
 * 선택 즉시 서버에 업로드하고 file_url 등을 상위 폼 state(BoardAttachmentRef[])로 올린다.
 * 작성/수정 페이지에서 공용으로 쓴다.
 */

import { useRef } from "react";
import { Button, TextButton } from "@wanteddev/wds";

import {
  BOARD_ATTACHMENT_ACCEPT,
  BOARD_MAX_ATTACHMENTS,
  BOARD_MAX_ATTACHMENT_BYTES,
  BoardApiError,
  BoardAttachmentRef,
  formatFileSize,
  isBoardAttachmentAllowed,
  uploadBoardAttachment,
} from "@/features/admin-board/api/board";

import styles from "./AttachmentPicker.module.css";

interface Props {
  value: BoardAttachmentRef[];
  onChange: (next: BoardAttachmentRef[]) => void;
  uploadingCount: number;
  onUploadingCountChange: (updater: (prev: number) => number) => void;
  onError: (message: string | null) => void;
  disabled?: boolean;
}

export function AttachmentPicker({
  value,
  onChange,
  uploadingCount,
  onUploadingCountChange,
  onError,
  disabled,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const full = value.length >= BOARD_MAX_ATTACHMENTS;

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    onError(null);

    const room = BOARD_MAX_ATTACHMENTS - value.length;
    if (room <= 0) {
      onError(`파일은 최대 ${BOARD_MAX_ATTACHMENTS}개까지 첨부할 수 있습니다.`);
      return;
    }

    const toUpload = Array.from(files).slice(0, room);
    for (const file of toUpload) {
      if (!isBoardAttachmentAllowed(file.name)) {
        onError(
          `첨부할 수 없는 형식입니다: ${file.name} (PDF·ZIP·워드·아래한글·엑셀·TXT·이미지만 가능)`,
        );
        continue;
      }
      if (file.size > BOARD_MAX_ATTACHMENT_BYTES) {
        onError(`각 파일은 20MB 이하만 첨부할 수 있습니다 (${file.name}).`);
        continue;
      }

      onUploadingCountChange((c) => c + 1);
      try {
        const result = await uploadBoardAttachment(file);
        onChange([
          ...value,
          {
            file_url: result.file_url,
            file_name: result.file_name,
            mime_type: result.mime_type,
            size_bytes: result.size_bytes,
          },
        ]);
      } catch (err) {
        onError(
          err instanceof BoardApiError
            ? err.message
            : "파일 업로드에 실패했습니다.",
        );
      } finally {
        onUploadingCountChange((c) => Math.max(0, c - 1));
      }
    }

    if (inputRef.current) inputRef.current.value = "";
  }

  function removeAttachment(fileUrl: string) {
    onChange(value.filter((a) => a.file_url !== fileUrl));
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.pickRow}>
        <input
          ref={inputRef}
          id="board-attachment-input"
          type="file"
          accept={BOARD_ATTACHMENT_ACCEPT}
          multiple
          className={styles.hiddenInput}
          onChange={(e) => handleFiles(e.target.files)}
          disabled={disabled || full || uploadingCount > 0}
        />
        <Button
          as="label"
          htmlFor="board-attachment-input"
          variant="outlined"
          color="assistive"
          size="small"
          disabled={disabled || full || uploadingCount > 0}
          loading={uploadingCount > 0}
        >
          {uploadingCount > 0
            ? "업로드 중…"
            : full
              ? `최대 ${BOARD_MAX_ATTACHMENTS}개 첨부됨`
              : "파일 첨부"}
        </Button>
        <p className={styles.hint}>
          PDF·ZIP·워드·아래한글·엑셀·TXT·이미지, 각 20MB 이하, 최대{" "}
          {BOARD_MAX_ATTACHMENTS}개
        </p>
      </div>

      {value.length > 0 ? (
        <ul className={styles.list}>
          {value.map((a) => (
            <li key={a.file_url} className={styles.item}>
              <span className={styles.fileName} title={a.file_name}>
                📎 {a.file_name}
              </span>
              <span className={styles.fileSize}>
                {formatFileSize(a.size_bytes)}
              </span>
              <TextButton
                color="assistive"
                size="small"
                onClick={() => removeAttachment(a.file_url)}
                disabled={disabled}
              >
                삭제
              </TextButton>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
