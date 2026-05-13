"use client";

/** /my/inquiries/new — 1:1 문의 작성 페이지. 0030.
 *
 * 타입 선택(6종) + 제목 + 본문 + 이미지 첨부(최대 5장, 각 5MB, jpg/png/webp).
 * 제출 후 즉시 목록(/my/inquiries)으로 이동.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Button, Option, Select, TextButton } from "@wanteddev/wds";

import { TopNav } from "@/components/layout/TopNav";
import { Footer } from "@/components/layout/Footer";
import { ApiError } from "@/types/api";
import { useSessionStore } from "@/stores/session-store";

import {
  type AttachmentRef,
  type InquiryType,
  INQUIRY_TYPE_LABELS,
  uploadInquiryImage,
} from "@/features/support/api";
import { useSubmitInquiry } from "@/features/support/hooks/useSubmitInquiry";

import styles from "./page.module.css";

const SUBJECT_MAX = 200;
const BODY_MAX = 5000;
const MAX_FILES = 5;
const MAX_BYTES = 5 * 1024 * 1024;
const ALLOWED_MIMES = new Set(["image/png", "image/jpeg", "image/webp"]);

const TYPE_OPTIONS: InquiryType[] = [
  "billing",
  "account",
  "usage",
  "bug",
  "suggestion",
  "other",
];

interface PendingAttachment extends AttachmentRef {
  preview_url: string;
}

export default function NewInquiryPage() {
  const router = useRouter();
  const user = useSessionStore((s) => s.user);
  const openPopup = useSessionStore((s) => s.openPopup);

  const [inquiryType, setInquiryType] = useState<InquiryType>("usage");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [uploadingCount, setUploadingCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const submit = useSubmitInquiry();

  useEffect(() => {
    if (user === null) {
      openPopup("email");
      router.replace("/?login=required");
    }
  }, [user, openPopup, router]);

  useEffect(() => {
    // 컴포넌트 언마운트 시 미사용 ObjectURL 회수 — 메모리 누수 방지.
    return () => {
      attachments.forEach((a) => URL.revokeObjectURL(a.preview_url));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (user === null) return null;

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setError(null);

    const room = MAX_FILES - attachments.length;
    if (room <= 0) {
      setError(`이미지는 최대 ${MAX_FILES}장까지 첨부할 수 있습니다.`);
      return;
    }

    const toUpload = Array.from(files).slice(0, room);

    for (const file of toUpload) {
      if (!ALLOWED_MIMES.has(file.type)) {
        setError("PNG·JPG·WEBP 이미지만 첨부할 수 있습니다.");
        continue;
      }
      if (file.size > MAX_BYTES) {
        setError(`각 이미지는 5MB 이하만 첨부할 수 있습니다 (${file.name}).`);
        continue;
      }

      setUploadingCount((c) => c + 1);
      try {
        const result = await uploadInquiryImage(file);
        setAttachments((prev) => {
          if (prev.length >= MAX_FILES) return prev;
          return [
            ...prev,
            {
              file_url: result.file_url,
              file_name: result.file_name,
              mime_type: result.mime_type,
              size_bytes: result.size_bytes,
              preview_url: URL.createObjectURL(file),
            },
          ];
        });
      } catch (err) {
        if (err instanceof Error) setError(err.message);
        else setError("이미지 업로드에 실패했습니다.");
      } finally {
        setUploadingCount((c) => Math.max(0, c - 1));
      }
    }

    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function removeAttachment(file_url: string) {
    setAttachments((prev) => {
      const target = prev.find((a) => a.file_url === file_url);
      if (target) URL.revokeObjectURL(target.preview_url);
      return prev.filter((a) => a.file_url !== file_url);
    });
  }

  function validate(): string | null {
    if (subject.trim().length === 0) return "제목을 입력해주세요.";
    if (subject.length > SUBJECT_MAX)
      return `제목은 ${SUBJECT_MAX}자 이내로 입력해주세요.`;
    if (body.trim().length === 0) return "문의 내용을 입력해주세요.";
    if (body.length > BODY_MAX)
      return `문의 내용은 ${BODY_MAX}자 이내로 입력해주세요.`;
    return null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const v = validate();
    if (v) {
      setError(v);
      return;
    }
    if (uploadingCount > 0) {
      setError("이미지 업로드가 끝난 뒤 제출해주세요.");
      return;
    }
    setError(null);
    try {
      await submit.mutateAsync({
        inquiry_type: inquiryType,
        subject,
        body,
        attachments: attachments.map((a) => ({
          file_url: a.file_url,
          file_name: a.file_name,
          mime_type: a.mime_type,
          size_bytes: a.size_bytes,
        })),
      });
      router.push("/my/inquiries");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === "RATE_LIMITED") {
          setError("잠시 후 다시 시도해주세요 (분당 3회 제한).");
        } else {
          setError(err.message || "잠시 문제가 생겼어요. 다시 시도해주세요.");
        }
      } else {
        setError("잠시 문제가 생겼어요. 다시 시도해주세요.");
      }
    }
  }

  return (
    <>
      <TopNav />
      <main className={styles.container}>
        <header className={styles.header}>
          <h1 className={styles.heading}>1:1 문의 작성</h1>
          <p className={styles.lead}>
            영업일 기준 1~2일 내 답변을 알림톡으로 보내드리고, 답변 내용은
            <Link href="/my/inquiries" className={styles.inlineLink}>
              내 문의 목록
            </Link>
            에서도 확인할 수 있어요.
          </p>
        </header>

        <form className={styles.form} onSubmit={handleSubmit} noValidate>
          <div className={styles.field}>
            <label htmlFor="inquiry-type" className={styles.label}>
              문의 유형
            </label>
            <Select
              name="inquiry-type"
              value={inquiryType}
              onChange={(v) => setInquiryType(v as InquiryType)}
              width="100%"
            >
              {TYPE_OPTIONS.map((t) => (
                <Option key={t} value={t}>
                  {INQUIRY_TYPE_LABELS[t]}
                </Option>
              ))}
            </Select>
          </div>

          <div className={styles.field}>
            <label htmlFor="inquiry-subject" className={styles.label}>
              제목
            </label>
            <input
              id="inquiry-subject"
              type="text"
              className={styles.input}
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              maxLength={SUBJECT_MAX}
              placeholder="예: 결제가 두 번 청구된 것 같아요"
              required
            />
          </div>

          <div className={styles.field}>
            <label htmlFor="inquiry-body" className={styles.label}>
              문의 내용
            </label>
            <textarea
              id="inquiry-body"
              className={styles.textarea}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              maxLength={BODY_MAX}
              rows={10}
              placeholder="어떤 도움이 필요하신가요? 상황을 자세히 적어주실수록 빠른 답변에 도움이 됩니다."
              required
            />
            <div className={styles.counter}>
              {body.length} / {BODY_MAX}
            </div>
          </div>

          <div className={styles.field}>
            <span className={styles.label}>
              첨부 이미지 ({attachments.length}/{MAX_FILES})
            </span>
            <div className={styles.attachmentArea}>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                multiple
                onChange={(e) => handleFiles(e.target.files)}
                className={styles.fileInput}
                disabled={
                  attachments.length >= MAX_FILES || uploadingCount > 0
                }
                id="inquiry-files"
              />
              <Button
                as="label"
                htmlFor="inquiry-files"
                variant="outlined"
                color="assistive"
                size="small"
                disabled={attachments.length >= MAX_FILES || uploadingCount > 0}
                loading={uploadingCount > 0}
              >
                {uploadingCount > 0
                  ? "업로드 중…"
                  : attachments.length >= MAX_FILES
                    ? "최대 5장 첨부됨"
                    : "이미지 추가"}
              </Button>
              <p className={styles.fileHint}>
                JPG·PNG·WEBP, 각 5MB 이하, 최대 5장
              </p>
            </div>

            {attachments.length > 0 ? (
              <ul className={styles.attachmentList}>
                {attachments.map((a) => (
                  <li key={a.file_url} className={styles.attachmentItem}>
                    <img
                      src={a.preview_url}
                      alt={a.file_name}
                      className={styles.thumbnail}
                    />
                    <div className={styles.thumbMeta}>
                      <span className={styles.thumbName}>{a.file_name}</span>
                      <TextButton
                        color="assistive"
                        size="small"
                        onClick={() => removeAttachment(a.file_url)}
                      >
                        삭제
                      </TextButton>
                    </div>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>

          {error ? (
            <p role="alert" className={styles.error}>
              {error}
            </p>
          ) : null}

          <div className={styles.actions}>
            <Button
              as={Link}
              href="/my/inquiries"
              variant="outlined"
              color="assistive"
              size="medium"
            >
              취소
            </Button>
            <Button
              type="submit"
              variant="solid"
              color="primary"
              size="medium"
              loading={submit.isPending}
              disabled={submit.isPending || uploadingCount > 0}
            >
              {submit.isPending ? "제출 중…" : "문의 제출"}
            </Button>
          </div>
        </form>
      </main>
      <Footer />
    </>
  );
}
