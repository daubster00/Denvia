"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Option, Select } from "@wanteddev/wds";

import { toEditorHtml } from "@/lib/asset-url";
import {
  BoardApiError,
  BoardCommentItem,
  BoardPostDetail,
  BoardPostStatus,
  createBoardComment,
  deleteBoardComment,
  deleteBoardPost,
  fetchBoardMeta,
  fetchBoardPost,
  updateBoardComment,
  updateBoardPostStatus,
} from "@/features/admin-board/api/board";

import styles from "./page.module.css";

const STATUS_CLASS: Record<BoardPostStatus, string> = {
  review: styles.statusReview,
  in_progress: styles.statusInProgress,
  completed: styles.statusCompleted,
  rejected: styles.statusRejected,
  on_hold: styles.statusOnHold,
};

function formatKoreanDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}

export default function BoardPostDetailPage(
  props: { params: Promise<{ postId: string }> },
) {
  const { postId: postIdStr } = use(props.params);
  const postId = Number(postIdStr);
  const router = useRouter();
  const queryClient = useQueryClient();

  const [commentDraft, setCommentDraft] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [editingCommentId, setEditingCommentId] = useState<number | null>(null);
  const [editingCommentText, setEditingCommentText] = useState("");
  const [confirmDeletePost, setConfirmDeletePost] = useState(false);
  const [confirmDeleteComment, setConfirmDeleteComment] = useState<number | null>(
    null,
  );

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

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-board", "post", postId] });
    queryClient.invalidateQueries({ queryKey: ["admin-board", "posts"] });
  };

  const statusMut = useMutation({
    mutationFn: (next: BoardPostStatus) =>
      updateBoardPostStatus(postId, next),
    onSuccess: invalidate,
    onError: (err: unknown) => {
      setErrorMsg(
        err instanceof BoardApiError ? err.message : "상태 변경에 실패했습니다.",
      );
    },
  });

  const createCommentMut = useMutation({
    mutationFn: (content: string) => createBoardComment(postId, content),
    onSuccess: () => {
      setCommentDraft("");
      setErrorMsg(null);
      invalidate();
    },
    onError: (err: unknown) => {
      setErrorMsg(
        err instanceof BoardApiError ? err.message : "댓글 등록에 실패했습니다.",
      );
    },
  });

  const updateCommentMut = useMutation({
    mutationFn: (vars: { commentId: number; content: string }) =>
      updateBoardComment(vars.commentId, vars.content),
    onSuccess: () => {
      setEditingCommentId(null);
      setEditingCommentText("");
      invalidate();
    },
    onError: (err: unknown) => {
      setErrorMsg(
        err instanceof BoardApiError ? err.message : "댓글 수정에 실패했습니다.",
      );
    },
  });

  const deleteCommentMut = useMutation({
    mutationFn: (commentId: number) => deleteBoardComment(commentId),
    onSuccess: () => {
      setConfirmDeleteComment(null);
      invalidate();
    },
    onError: (err: unknown) => {
      setErrorMsg(
        err instanceof BoardApiError ? err.message : "댓글 삭제에 실패했습니다.",
      );
      setConfirmDeleteComment(null);
    },
  });

  const deletePostMut = useMutation({
    mutationFn: () => deleteBoardPost(postId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-board", "posts"] });
      router.replace("/admin/board");
    },
    onError: (err: unknown) => {
      setErrorMsg(
        err instanceof BoardApiError ? err.message : "글 삭제에 실패했습니다.",
      );
      setConfirmDeletePost(false);
    },
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
        <Link href="/admin/board" className={styles.secondaryBtn}>
          목록으로
        </Link>
      </div>
    );
  }

  const post: BoardPostDetail = postQuery.data;
  const categoryLabel =
    metaQuery.data?.categories.find((c) => c.key === post.category)?.label ??
    post.category;
  const statusLabel =
    metaQuery.data?.statuses.find((s) => s.key === post.status)?.label ??
    post.status;

  const onSubmitComment = (e: React.FormEvent) => {
    e.preventDefault();
    if (!commentDraft.trim()) return;
    createCommentMut.mutate(commentDraft.trim());
  };

  const startEditComment = (c: BoardCommentItem) => {
    setEditingCommentId(c.id);
    setEditingCommentText(c.content);
  };

  return (
    <div className={styles.page}>
      <nav className={styles.crumbs}>
        <Link href="/admin/board">← 수정요청 게시판</Link>
        <span>/</span>
        <span>#{post.id}</span>
      </nav>

      <article className={styles.postCard}>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>{post.title}</h1>
          <div className={styles.metaRow}>
            <span className={styles.categoryChip}>{categoryLabel}</span>
            <span className={`${styles.statusBadge} ${STATUS_CLASS[post.status]}`}>
              {statusLabel}
            </span>
            <span>
              작성자{" "}
              <span className={styles.author}>{post.author_display}</span>
            </span>
            <span>· {formatKoreanDateTime(post.created_at)}</span>
            {post.updated_at !== post.created_at && (
              <span>(수정 {formatKoreanDateTime(post.updated_at)})</span>
            )}
          </div>
        </div>

        <div className={styles.statusBlock}>
          <span className={styles.statusBlockLabel}>상태</span>
          {post.can_change_status ? (
            <div className={styles.statusSelectWrap}>
              <Select
                value={post.status}
                onChange={(v) => statusMut.mutate(v as BoardPostStatus)}
                disabled={statusMut.isPending}
                width="180px"
              >
                {metaQuery.data?.statuses.map((s) => (
                  <Option key={s.key} value={s.key}>
                    {s.label}
                  </Option>
                ))}
              </Select>
            </div>
          ) : (
            <span className={`${styles.statusBadge} ${STATUS_CLASS[post.status]}`}>
              {statusLabel}
            </span>
          )}
          <span className={styles.statusNote}>
            {post.can_change_status
              ? "btmdesign 마스터 계정 — 상태 변경 가능"
              : "상태 변경은 btmdesign 마스터 계정만 가능합니다"}
          </span>
        </div>

        <div
          className={styles.content}
          dangerouslySetInnerHTML={{ __html: toEditorHtml(post.content_html) }}
        />

        {errorMsg ? <p className={styles.errorText}>{errorMsg}</p> : null}

        {post.can_edit && (
          <div className={styles.actions}>
            <button
              type="button"
              className={styles.secondaryBtn}
              onClick={() => router.push(`/admin/board/${post.id}/edit`)}
            >
              글 수정
            </button>
            <button
              type="button"
              className={styles.dangerBtn}
              onClick={() => setConfirmDeletePost(true)}
            >
              글 삭제
            </button>
          </div>
        )}
      </article>

      <section className={styles.commentsSection}>
        <h2 className={styles.commentsTitle}>
          댓글 {post.comments.length}개
        </h2>

        {post.comments.length === 0 ? (
          <div className={styles.empty}>아직 댓글이 없습니다.</div>
        ) : (
          <ul className={styles.commentList}>
            {post.comments.map((c) => (
              <li key={c.id} className={styles.commentCard}>
                <div className={styles.commentMeta}>
                  <span>
                    <span className={styles.commentAuthor}>
                      {c.author_display}
                    </span>{" "}
                    · {formatKoreanDateTime(c.created_at)}
                    {c.updated_at !== c.created_at && (
                      <span> (수정됨)</span>
                    )}
                  </span>
                  {c.can_edit && editingCommentId !== c.id && (
                    <span className={styles.commentActions}>
                      <button
                        type="button"
                        className={styles.commentActionBtn}
                        onClick={() => startEditComment(c)}
                      >
                        수정
                      </button>
                      <button
                        type="button"
                        className={`${styles.commentActionBtn} ${styles.commentActionDanger}`}
                        onClick={() => setConfirmDeleteComment(c.id)}
                      >
                        삭제
                      </button>
                    </span>
                  )}
                </div>
                {editingCommentId === c.id ? (
                  <div className={styles.commentEditArea}>
                    <textarea
                      className={styles.commentTextarea}
                      value={editingCommentText}
                      onChange={(e) => setEditingCommentText(e.target.value)}
                      maxLength={2000}
                    />
                    <div className={styles.commentFormActions}>
                      <button
                        type="button"
                        className={styles.secondaryBtn}
                        onClick={() => {
                          setEditingCommentId(null);
                          setEditingCommentText("");
                        }}
                      >
                        취소
                      </button>
                      <button
                        type="button"
                        className={styles.primaryBtn}
                        disabled={
                          updateCommentMut.isPending ||
                          !editingCommentText.trim()
                        }
                        onClick={() =>
                          updateCommentMut.mutate({
                            commentId: c.id,
                            content: editingCommentText.trim(),
                          })
                        }
                      >
                        저장
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className={styles.commentBody}>{c.content}</p>
                )}
              </li>
            ))}
          </ul>
        )}

        <form className={styles.commentForm} onSubmit={onSubmitComment}>
          <textarea
            className={styles.commentTextarea}
            placeholder="댓글을 입력해주세요"
            value={commentDraft}
            onChange={(e) => setCommentDraft(e.target.value)}
            maxLength={2000}
          />
          <div className={styles.commentFormActions}>
            <button
              type="submit"
              className={styles.primaryBtn}
              disabled={createCommentMut.isPending || !commentDraft.trim()}
            >
              {createCommentMut.isPending ? "등록 중…" : "댓글 등록"}
            </button>
          </div>
        </form>
      </section>

      {confirmDeletePost && (
        <div className={styles.confirmBackdrop}>
          <div className={styles.confirmModal}>
            <h3 className={styles.confirmTitle}>글을 삭제하시겠어요?</h3>
            <p className={styles.confirmBody}>
              삭제한 글과 댓글은 복구할 수 없습니다.
            </p>
            <div className={styles.confirmActions}>
              <button
                type="button"
                className={styles.secondaryBtn}
                onClick={() => setConfirmDeletePost(false)}
                disabled={deletePostMut.isPending}
              >
                취소
              </button>
              <button
                type="button"
                className={styles.dangerBtn}
                onClick={() => deletePostMut.mutate()}
                disabled={deletePostMut.isPending}
              >
                {deletePostMut.isPending ? "삭제 중…" : "삭제"}
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmDeleteComment !== null && (
        <div className={styles.confirmBackdrop}>
          <div className={styles.confirmModal}>
            <h3 className={styles.confirmTitle}>댓글을 삭제하시겠어요?</h3>
            <div className={styles.confirmActions}>
              <button
                type="button"
                className={styles.secondaryBtn}
                onClick={() => setConfirmDeleteComment(null)}
                disabled={deleteCommentMut.isPending}
              >
                취소
              </button>
              <button
                type="button"
                className={styles.dangerBtn}
                onClick={() =>
                  deleteCommentMut.mutate(confirmDeleteComment)
                }
                disabled={deleteCommentMut.isPending}
              >
                {deleteCommentMut.isPending ? "삭제 중…" : "삭제"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
