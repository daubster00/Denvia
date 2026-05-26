"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  fetchUsers,
  type UserSearchItem,
} from "@/features/admin-users/api/users";

import {
  NoticeApiError,
  noticeFormSchema,
  type NoticeFormInput,
  type NoticeTargetSegment,
} from "../api/notice";
import styles from "./NoticeCreateDialog.module.css";

export type CreateTargetType = "segment" | "user";

export interface NoticeCreateSubmitPayload {
  target_type: CreateTargetType;
  title: string;
  body_html: string;
  /** target_type='segment' 일 때만 채워짐 */
  target_segment?: NoticeTargetSegment;
  /** target_type='user' 일 때만 채워짐 */
  target_user_id?: number;
  target_user_email?: string;
}

interface NoticeCreateDialogProps {
  isSubmitting: boolean;
  errorMessage: string | null;
  onClose: () => void;
  onSubmit: (payload: NoticeCreateSubmitPayload) => void;
}

type TargetChoice =
  | { kind: "segment"; value: NoticeTargetSegment; label: string }
  | { kind: "user"; label: "특정 사용자" };

const TARGET_CHOICES: TargetChoice[] = [
  { kind: "segment", value: "all", label: "전체" },
  { kind: "segment", value: "doctor", label: "치과의사" },
  { kind: "segment", value: "hygienist", label: "치과위생사" },
  { kind: "segment", value: "student_other", label: "학생/기타" },
  { kind: "user", label: "특정 사용자" },
];

const USER_SEARCH_DEBOUNCE_MS = 250;
const USER_SEARCH_PER_PAGE = 8;

function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

export function NoticeCreateDialog({
  isSubmitting,
  errorMessage,
  onClose,
  onSubmit,
}: NoticeCreateDialogProps) {
  const [title, setTitle] = useState("");
  const [bodyHtml, setBodyHtml] = useState("");
  const [targetKind, setTargetKind] = useState<CreateTargetType>("segment");
  const [targetSegment, setTargetSegment] =
    useState<NoticeTargetSegment>("all");
  const [userQuery, setUserQuery] = useState("");
  const [selectedUser, setSelectedUser] = useState<UserSearchItem | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{
    title?: string;
    body_html?: string;
    target?: string;
  }>({});
  const titleRef = useRef<HTMLInputElement>(null);

  const debouncedQuery = useDebouncedValue(userQuery.trim(), USER_SEARCH_DEBOUNCE_MS);

  const userSearchQuery = useQuery({
    queryKey: ["admin", "notice-create-user-search", debouncedQuery],
    queryFn: () =>
      fetchUsers({
        q: debouncedQuery,
        withdrawn: false,
        per_page: USER_SEARCH_PER_PAGE,
      }),
    enabled: targetKind === "user" && debouncedQuery.length > 0 && !selectedUser,
    staleTime: 30_000,
  });

  useEffect(() => {
    titleRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !isSubmitting) onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, isSubmitting]);

  const searchResults = useMemo(() => {
    if (targetKind !== "user") return [];
    if (selectedUser) return [];
    if (debouncedQuery.length === 0) return [];
    return userSearchQuery.data?.items ?? [];
  }, [targetKind, selectedUser, debouncedQuery, userSearchQuery.data]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    if (targetKind === "user" && !selectedUser) {
      setFieldErrors((prev) => ({
        ...prev,
        target: "받는 사용자를 검색해서 선택해주세요.",
      }));
      return;
    }

    const parsed = noticeFormSchema.safeParse({
      title,
      body_html: bodyHtml,
      target_segment: targetSegment,
    });
    if (!parsed.success) {
      const next: { title?: string; body_html?: string } = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0];
        if (key === "title") next.title = issue.message;
        if (key === "body_html") next.body_html = issue.message;
      }
      setFieldErrors(next);
      return;
    }
    setFieldErrors({});

    if (targetKind === "user" && selectedUser) {
      onSubmit({
        target_type: "user",
        title: parsed.data.title,
        body_html: parsed.data.body_html,
        target_user_id: selectedUser.user_id,
        target_user_email: selectedUser.email,
      });
      return;
    }

    onSubmit({
      target_type: "segment",
      title: parsed.data.title,
      body_html: parsed.data.body_html,
      target_segment: parsed.data.target_segment,
    });
  }

  return (
    <>
      <div
        aria-hidden="true"
        className={styles.overlay}
        onClick={() => {
          if (!isSubmitting) onClose();
        }}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="notice-create-title"
        className={styles.dialog}
      >
        <header className={styles.header}>
          <h2 id="notice-create-title" className={styles.title}>
            새 쪽지 작성
          </h2>
          <p className={styles.caption}>
            전체/세그먼트 또는 특정 사용자에게 쪽지를 보냅니다. 저장 즉시 발송되며, 잘못 보낸 쪽지는 목록에서 삭제하면 회수됩니다.
          </p>
        </header>

        <form className={styles.form} onSubmit={handleSubmit}>
          <label className={styles.field}>
            <span className={styles.label}>제목</span>
            <input
              ref={titleRef}
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              className={styles.input}
              disabled={isSubmitting}
              required
            />
            {fieldErrors.title && (
              <span className={styles.error}>{fieldErrors.title}</span>
            )}
          </label>

          <label className={styles.field}>
            <span className={styles.label}>본문</span>
            <textarea
              value={bodyHtml}
              onChange={(e) => setBodyHtml(e.target.value)}
              maxLength={20000}
              rows={8}
              className={styles.textarea}
              disabled={isSubmitting}
              required
            />
            <span className={styles.hint}>
              HTML 태그를 쓸 수 있지만, 안전한 태그만 통과합니다.
            </span>
            {fieldErrors.body_html && (
              <span className={styles.error}>{fieldErrors.body_html}</span>
            )}
          </label>

          <div className={styles.field}>
            <span className={styles.label}>받는 대상</span>
            <div className={styles.targetGroup} role="radiogroup" aria-label="받는 대상">
              {TARGET_CHOICES.map((choice) => {
                const isActive =
                  choice.kind === "user"
                    ? targetKind === "user"
                    : targetKind === "segment" && targetSegment === choice.value;
                const id =
                  choice.kind === "user"
                    ? "target-user"
                    : `target-segment-${choice.value}`;
                return (
                  <label
                    key={id}
                    htmlFor={id}
                    className={`${styles.targetOption} ${isActive ? styles.targetOptionActive : ""}`}
                  >
                    <input
                      id={id}
                      type="radio"
                      name="notice-target"
                      className={styles.targetRadio}
                      checked={isActive}
                      disabled={isSubmitting}
                      onChange={() => {
                        if (choice.kind === "user") {
                          setTargetKind("user");
                        } else {
                          setTargetKind("segment");
                          setTargetSegment(choice.value);
                          setSelectedUser(null);
                          setUserQuery("");
                        }
                        setFieldErrors((prev) => ({ ...prev, target: undefined }));
                      }}
                    />
                    {choice.label}
                  </label>
                );
              })}
            </div>
            {fieldErrors.target && (
              <span className={styles.error}>{fieldErrors.target}</span>
            )}
          </div>

          {targetKind === "user" && (
            <div className={styles.field}>
              <span className={styles.label}>받는 사용자</span>
              {selectedUser ? (
                <span className={styles.selectedChip}>
                  <span className={styles.selectedChipEmail}>
                    {selectedUser.email}
                  </span>
                  <button
                    type="button"
                    className={styles.selectedChipClear}
                    aria-label="선택 해제"
                    disabled={isSubmitting}
                    onClick={() => {
                      setSelectedUser(null);
                      setUserQuery("");
                    }}
                  >
                    ×
                  </button>
                </span>
              ) : (
                <div className={styles.searchBox}>
                  <input
                    type="text"
                    value={userQuery}
                    onChange={(e) => setUserQuery(e.target.value)}
                    placeholder="이메일 또는 이름으로 검색"
                    className={styles.searchInput}
                    disabled={isSubmitting}
                    autoComplete="off"
                  />
                  {debouncedQuery.length > 0 && (
                    <>
                      {userSearchQuery.isPending ? (
                        <span className={styles.searchEmpty}>검색 중…</span>
                      ) : userSearchQuery.error ? (
                        <span className={styles.searchEmpty}>
                          사용자 검색에 실패했습니다.
                        </span>
                      ) : searchResults.length === 0 ? (
                        <span className={styles.searchEmpty}>
                          일치하는 사용자가 없습니다.
                        </span>
                      ) : (
                        <ul className={styles.searchResults} role="listbox">
                          {searchResults.map((u) => (
                            <li
                              key={u.user_id}
                              role="option"
                              aria-selected="false"
                              tabIndex={0}
                              className={styles.searchResultItem}
                              onClick={() => setSelectedUser(u)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  setSelectedUser(u);
                                }
                              }}
                            >
                              <span className={styles.searchResultEmail}>
                                {u.email}
                              </span>
                              <span className={styles.searchResultMeta}>
                                #{u.user_id}
                                {u.segment ? ` · ${u.segment}` : ""}
                                {u.subscription_status
                                  ? ` · ${u.subscription_status}`
                                  : ""}
                              </span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          )}

          {errorMessage && (
            <p className={styles.errorBox} role="alert">
              {errorMessage}
            </p>
          )}

          <footer className={styles.footer}>
            <button
              type="button"
              className={styles.cancelBtn}
              onClick={onClose}
              disabled={isSubmitting}
            >
              취소
            </button>
            <button
              type="submit"
              className={styles.submitBtn}
              disabled={isSubmitting}
            >
              {isSubmitting ? "발송 중…" : "발송"}
            </button>
          </footer>
        </form>
      </div>
    </>
  );
}

export type { NoticeFormInput };
export { NoticeApiError };
