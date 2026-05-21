"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Option, Select } from "@wanteddev/wds";

import { RichTextEditor } from "@/components/editor/RichTextEditor";
import {
  BoardApiError,
  BoardCategory,
  BoardPostFormInput,
  fetchBoardMeta,
  fetchBoardPost,
  updateBoardPost,
  uploadBoardImage,
} from "@/features/admin-board/api/board";

import styles from "../../form.module.css";

export default function EditBoardPostPage(
  props: { params: Promise<{ postId: string }> },
) {
  const { postId: postIdStr } = use(props.params);
  const postId = Number(postIdStr);
  const router = useRouter();
  const queryClient = useQueryClient();

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

  const [category, setCategory] = useState<BoardCategory | "">("");
  const [title, setTitle] = useState("");
  const [contentHtml, setContentHtml] = useState("");
  const [initialised, setInitialised] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (postQuery.data && !initialised) {
      setCategory(postQuery.data.category);
      setTitle(postQuery.data.title);
      setContentHtml(postQuery.data.content_html);
      setInitialised(true);
    }
  }, [postQuery.data, initialised]);

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

  if (postQuery.isLoading || !initialised) {
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
    updateMut.mutate({ category, title: title.trim(), content_html: contentHtml });
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
            {metaQuery.data?.categories.map((c) => (
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
            disabled={updateMut.isPending}
          >
            {updateMut.isPending ? "저장 중…" : "저장"}
          </button>
        </div>
      </form>
    </div>
  );
}
