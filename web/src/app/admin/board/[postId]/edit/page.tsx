"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Option, Select } from "@wanteddev/wds";

import { RichTextEditor } from "@/components/editor/RichTextEditor";
import {
  BoardApiError,
  BoardAttachmentRef,
  BoardCategory,
  BoardPostDetail,
  BoardPostFormInput,
  fetchBoardMeta,
  fetchBoardPost,
  updateBoardPost,
  uploadBoardImage,
} from "@/features/admin-board/api/board";
import { AttachmentPicker } from "@/features/admin-board/components/AttachmentPicker";

import styles from "../../form.module.css";

export default function EditBoardPostPage(
  props: { params: Promise<{ postId: string }> },
) {
  const { postId: postIdStr } = use(props.params);
  const postId = Number(postIdStr);
  const router = useRouter();

  const metaQuery = useQuery({
    queryKey: ["admin-board", "meta"],
    queryFn: fetchBoardMeta,
    staleTime: 5 * 60_000,
  });

  const postQuery = useQuery({
    queryKey: ["admin-board", "post", postId],
    queryFn: () => fetchBoardPost(postId),
    enabled: !Number.isNaN(postId),
  });

  if (postQuery.isLoading) {
    return <div className={styles.page}>불러오는 중…</div>;
  }
  if (postQuery.isError || !postQuery.data) {
    return (
      <div className={styles.page}>
        <p className={styles.errorText}>
          {postQuery.error instanceof BoardApiError
            ? postQuery.error.message
            : "글을 불러오지 못했습니다."}
        </p>
      </div>
    );
  }
  if (!postQuery.data.can_edit) {
    return (
      <div className={styles.page}>
        <p className={styles.errorText}>
          본인이 작성한 글만 수정할 수 있습니다.
        </p>
        <button
          type="button"
          className={styles.secondaryBtn}
          onClick={() => router.replace(`/admin/board/${postId}`)}
        >
          상세로 돌아가기
        </button>
      </div>
    );
  }

  return (
    <EditForm
      postId={postId}
      post={postQuery.data}
      categories={metaQuery.data?.categories ?? []}
    />
  );
}

function EditForm({
  postId,
  post,
  categories,
}: {
  postId: number;
  post: BoardPostDetail;
  categories: { key: BoardCategory; label: string }[];
}) {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [category, setCategory] = useState<BoardCategory | "">(
    post.category as BoardCategory | "",
  );
  const [title, setTitle] = useState(post.title);
  const [contentHtml, setContentHtml] = useState(post.content_html);
  const [attachments, setAttachments] = useState<BoardAttachmentRef[]>(
    post.attachments.map((a) => ({
      file_url: a.file_url,
      file_name: a.file_name,
      mime_type: a.mime_type,
      size_bytes: a.size_bytes,
    })),
  );
  const [uploadingCount, setUploadingCount] = useState(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const updateMut = useMutation({
    mutationFn: (input: BoardPostFormInput) => updateBoardPost(postId, input),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["admin-board", "posts"] });
      queryClient.setQueryData(["admin-board", "post", postId], data);
      router.replace(`/admin/board/${postId}`);
    },
    onError: (err: unknown) => {
      setErrorMsg(
        err instanceof BoardApiError ? err.message : "수정에 실패했습니다.",
      );
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
      setErrorMsg("파일 업로드가 끝난 뒤 저장해주세요.");
      return;
    }
    updateMut.mutate({
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
        <h1 className={styles.title}>글 수정</h1>
        <p className={styles.caption}>
          제목·본문·카테고리만 변경됩니다. 상태는 상세 페이지에서 별도로 변경하세요.
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
            {categories.map((c) => (
              <Option key={c.key} value={c.key}>
                {c.label}
              </Option>
            ))}
          </Select>
        </div>

        <div className={styles.row}>
          <label className={styles.label} htmlFor="board-edit-title">
            제목
          </label>
          <input
            id="board-edit-title"
            type="text"
            className={styles.input}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
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
        </div>

        <div className={styles.row}>
          <span className={styles.label}>첨부 파일</span>
          <AttachmentPicker
            value={attachments}
            onChange={setAttachments}
            uploadingCount={uploadingCount}
            onUploadingCountChange={setUploadingCount}
            onError={setErrorMsg}
            disabled={updateMut.isPending}
          />
        </div>

        {errorMsg ? <p className={styles.errorText}>{errorMsg}</p> : null}

        <div className={styles.actions}>
          <button
            type="button"
            className={styles.secondaryBtn}
            onClick={() => router.back()}
            disabled={updateMut.isPending}
          >
            취소
          </button>
          <button
            type="submit"
            className={styles.primaryBtn}
            disabled={updateMut.isPending || uploadingCount > 0}
          >
            {updateMut.isPending ? "저장 중…" : "저장"}
          </button>
        </div>
      </form>
    </div>
  );
}
