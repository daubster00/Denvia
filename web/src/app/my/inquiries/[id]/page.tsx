"use client";

/** /my/inquiries/[id] — 본인 1:1 문의 상세. 0030.
 *
 * 문의 본문 + 첨부 이미지 + 관리자 답변 이력. 타인 row는 404.
 */

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@wanteddev/wds";

import { TopNav } from "@/components/layout/TopNav";
import { Footer } from "@/components/layout/Footer";
import { useSessionStore } from "@/stores/session-store";

import {
  type InquiryDetailResponse,
  INQUIRY_TYPE_LABELS,
  getMyInquiry,
} from "@/features/support/api";
import { InquiryStatusBadge } from "@/features/support/components/InquiryStatusBadge";

import styles from "./page.module.css";

const KST_DATETIME = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  try {
    return KST_DATETIME.format(new Date(value));
  } catch {
    return value;
  }
}

export default function MyInquiryDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const user = useSessionStore((s) => s.user);
  const openPopup = useSessionStore((s) => s.openPopup);

  const inquiryId = Number(params?.id);
  const validId = Number.isFinite(inquiryId) && inquiryId > 0;

  const { data, isLoading, isError, error } = useQuery<InquiryDetailResponse>({
    queryKey: ["my-inquiry", inquiryId],
    queryFn: () => getMyInquiry(inquiryId),
    enabled: user !== null && validId,
    staleTime: 10_000,
    retry: false,
  });

  useEffect(() => {
    if (user === null) {
      openPopup("email");
      router.replace("/?login=required");
    }
  }, [user, openPopup, router]);

  if (user === null) return null;

  return (
    <>
      <TopNav />
      <main className={styles.container}>
        <nav className={styles.crumbs} aria-label="경로">
          <Link href="/my/inquiries" className={styles.crumbLink}>
            ← 내 문의 목록
          </Link>
        </nav>

        {!validId || isError ? (
          <section className={styles.errorBox} role="alert">
            <h1 className={styles.errorTitle}>문의를 찾을 수 없습니다</h1>
            <p className={styles.errorHint}>
              삭제되었거나 다른 사용자의 문의일 수 있어요. 목록으로 돌아가
              주세요.
              {error instanceof Error ? (
                <span className={styles.errorDetail}>{error.message}</span>
              ) : null}
            </p>
            <Button
              as={Link}
              href="/my/inquiries"
              variant="outlined"
              color="assistive"
              size="small"
              sx={{ marginTop: "8px" }}
            >
              목록으로
            </Button>
          </section>
        ) : isLoading || !data ? (
          <p className={styles.loadingBox}>불러오는 중…</p>
        ) : (
          <>
            <section className={styles.summary}>
              <div className={styles.summaryHead}>
                <h1 className={styles.subject}>{data.subject}</h1>
                <InquiryStatusBadge status={data.status} />
              </div>
              <dl className={styles.meta}>
                <div className={styles.metaRow}>
                  <dt>유형</dt>
                  <dd>{INQUIRY_TYPE_LABELS[data.inquiry_type]}</dd>
                </div>
                <div className={styles.metaRow}>
                  <dt>접수일</dt>
                  <dd>{formatDateTime(data.created_at)}</dd>
                </div>
                <div className={styles.metaRow}>
                  <dt>답변 완료일</dt>
                  <dd>{formatDateTime(data.resolved_at)}</dd>
                </div>
              </dl>
            </section>

            <section className={styles.bodySection}>
              <h2 className={styles.sectionLabel}>문의 내용</h2>
              <pre className={styles.bodyText}>{data.body}</pre>
            </section>

            {data.attachments.length > 0 ? (
              <section className={styles.bodySection}>
                <h2 className={styles.sectionLabel}>
                  첨부 이미지 ({data.attachments.length}장)
                </h2>
                <ul className={styles.attachmentGrid}>
                  {data.attachments.map((att) => (
                    <li key={att.id} className={styles.attachmentItem}>
                      <a
                        href={att.file_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={styles.attachmentLink}
                      >
                        <img
                          src={att.file_url}
                          alt={att.file_name}
                          className={styles.attachmentThumb}
                          loading="lazy"
                        />
                        <span className={styles.attachmentName}>
                          {att.file_name}
                        </span>
                      </a>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            <section className={styles.bodySection} aria-label="관리자 답변">
              <h2 className={styles.sectionLabel}>관리자 답변</h2>
              {data.replies.length === 0 ? (
                <p className={styles.emptyReply}>
                  아직 답변이 등록되지 않았어요. 영업일 기준 1~2일 내에
                  답변드릴게요.
                </p>
              ) : (
                <ul className={styles.replyList}>
                  {data.replies.map((r) => (
                    <li key={r.reply_id} className={styles.replyItem}>
                      <p className={styles.replyMeta}>
                        관리자 · {formatDateTime(r.created_at)}
                      </p>
                      <div
                        className={styles.replyContent}
                        dangerouslySetInnerHTML={{ __html: r.reply_html_safe }}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </main>
      <Footer />
    </>
  );
}
