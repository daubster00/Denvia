"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Option, Select } from "@wanteddev/wds";

import { RichTextEditor } from "@/components/editor/RichTextEditor";
import {
  BoardApiError,
  BoardAttachmentRef,
  BoardCategory,
  BoardPostFormInput,
  createBoardPost,
  fetchBoardMeta,
  uploadBoardImage,
} from "@/features/admin-board/api/board";
import { AttachmentPicker } from "@/features/admin-board/components/AttachmentPicker";

import styles from "../form.module.css";

export default function NewBoardPostPage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const metaQuery = useQuery({
    queryKey: ["admin-board", "meta"],
    queryFn: fetchBoardMeta,
    staleTime: 5 * 60_000,
  });

  const [category, setCategory] = useState<BoardCategory | "">("");
  const [title, setTitle] = useState("");
  const [contentHtml, setContentHtml] = useState("");
  const [attachments, setAttachments] = useState<BoardAttachmentRef[]>([]);
  const [uploadingCount, setUploadingCount] = useState(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const createMut = useMutation({
    mutationFn: (input: BoardPostFormInput) => createBoardPost(input),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["admin-board", "posts"] });
      router.replace(`/admin/board/${data.id}`);
    },
    onError: (err: unknown) => {
      if (err instanceof BoardApiError) setErrorMsg(err.message);
      else setErrorMsg("등록에 실패했습니다.");
    },
  });

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    if (!category) {
      setErrorMsg("카테고리를 선택해주세요.");
      return;
    }
    if (!title.trim()) {
      setErrorMsg("제목을 입력해주세요.");
      return;
    }
    if (!contentHtml.trim() || contentHtml.trim() === "<p></p>") {
      setErrorMsg("본문을 입력해주세요.");
      return;
    }
    if (uploadingCount > 0) {
      setErrorMsg("파일 업로드가 끝난 뒤 등록해주세요.");
      return;
    }
    createMut.mutate({
      category,
      title: title.trim(),
      content_html: contentHtml,
      attachments,
    });
  };

  const handleImageUpload = async (file: File): Promise<string> => {
    const res = await uploadBoardImage(file);
    return res.file_url;
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>새 수정요청 글 작성</h1>
        <p className={styles.caption}>
          작성 즉시 상태는 "요청사항검토"로 등록됩니다.
        </p>
      </header>

      <form className={styles.form} onSubmit={onSubmit}>
        <div className={styles.row}>
          <span className={styles.label}>카테고리</span>
          <Select
            value={category}
            onChange={(v) => setCategory(v as BoardCategory | "")}
            placeholder="선택해주세요"
            width="100%"
          >
            {metaQuery.data?.categories.map((c) => (
              <Option key={c.key} value={c.key}>
                {c.label}
              </Option>
            ))}
          </Select>
        </div>

        <div className={styles.row}>
          <label className={styles.label} htmlFor="board-title">
            제목
          </label>
          <input
            id="board-title"
            type="text"
            className={styles.input}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="간결한 한 줄 제목"
            maxLength={200}
          />
        </div>

        <div className={styles.row}>
          <label className={styles.label}>본문</label>
          <div className={styles.editorWrap}>
            <RichTextEditor
              value={contentHtml}
              onChange={setContentHtml}
              ariaLabel="본문 에디터"
              onImageUpload={handleImageUpload}
            />
          </div>
          <p className={styles.helpText}>
            이미지(PNG·JPG·WEBP, 5MB 이하)는 도구막대의 "이미지" 버튼으로 본문에 넣을 수 있습니다.
          </p>
        </div>

        <div className={styles.row}>
          <span className={styles.label}>첨부 파일</span>
          <AttachmentPicker
            value={attachments}
            onChange={setAttachments}
            uploadingCount={uploadingCount}
            onUploadingCountChange={setUploadingCount}
            onError={setErrorMsg}
            disabled={createMut.isPending}
          />
        </div>

        {errorMsg ? <p className={styles.errorText}>{errorMsg}</p> : null}

        <div className={styles.actions}>
          <button
            type="button"
            className={styles.secondaryBtn}
            onClick={() => router.back()}
            disabled={createMut.isPending}
          >
            취소
          </button>
          <button
            type="submit"
            className={styles.primaryBtn}
            disabled={createMut.isPending || uploadingCount > 0}
          >
            {createMut.isPending ? "등록 중…" : "등록"}
          </button>
        </div>
      </form>
    </div>
  );
}
