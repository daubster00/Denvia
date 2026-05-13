"use client";

/** /my/inquiries — 본인 1:1 문의 게시판 목록. 0030. */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@wanteddev/wds";

import { TopNav } from "@/components/layout/TopNav";
import { Footer } from "@/components/layout/Footer";
import { useSessionStore } from "@/stores/session-store";

import {
  INQUIRY_TYPE_LABELS,
  type InquiryListResponse,
  listMyInquiries,
} from "@/features/support/api";
import { InquiryStatusBadge } from "@/features/support/components/InquiryStatusBadge";

import styles from "./page.module.css";

const PER_PAGE = 20;
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

export default function MyInquiriesPage() {
  const router = useRouter();
  const user = useSessionStore((s) => s.user);
  const openPopup = useSessionStore((s) => s.openPopup);
  const [page, setPage] = useState(1);

  const { data, isLoading, isError } = useQuery<InquiryListResponse>({
    queryKey: ["my-inquiries", page],
    queryFn: () => listMyInquiries(page, PER_PAGE),
    enabled: user !== null,
    staleTime: 30_000,
  });

  useEffect(() => {
    if (user === null) {
      openPopup("email");
      router.replace("/?login=required");
    }
  }, [user, openPopup, router]);

  if (user === null) return null;

  const totalPages =
    data && data.total > 0 ? Math.ceil(data.total / PER_PAGE) : 1;

  return (
    <>
      <TopNav />
      <main className={styles.container}>
        <header className={styles.header}>
          <div className={styles.headerText}>
            <h1 className={styles.heading}>1:1 문의</h1>
            <p className={styles.lead}>
              결제·계정·기능 사용법 등 궁금하신 점을 보내주세요. 영업일 기준
              1~2일 내 답변드립니다.
            </p>
          </div>
          <Button
            as={Link}
            href="/my/inquiries/new"
            variant="solid"
            color="primary"
            size="medium"
          >
            문의 작성
          </Button>
        </header>

        <section className={styles.tableSection} aria-label="문의 목록">
          {isError ? (
            <div className={styles.errorBox} role="alert">
              문의 목록을 불러오지 못했어요. 잠시 후 다시 시도해주세요.
            </div>
          ) : isLoading && !data ? (
            <div className={styles.emptyBox}>불러오는 중…</div>
          ) : !data || data.items.length === 0 ? (
            <div className={styles.emptyBox} role="status">
              <p className={styles.emptyTitle}>아직 작성한 문의가 없습니다</p>
              <p className={styles.emptyHint}>
                상단 ‘문의 작성’ 버튼으로 첫 문의를 남겨주세요.
              </p>
            </div>
          ) : (
            <>
              <table className={styles.table} aria-rowcount={data.total}>
                <thead>
                  <tr>
                    <th scope="col" className={styles.colNumber}>
                      번호
                    </th>
                    <th scope="col" className={styles.colType}>
                      유형
                    </th>
                    <th scope="col" className={styles.colSubject}>
                      제목
                    </th>
                    <th scope="col" className={styles.colStatus}>
                      상태
                    </th>
                    <th scope="col" className={styles.colDate}>
                      작성일
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((it) => (
                    <tr key={it.id} className={styles.row}>
                      <td className={styles.colNumber}>{it.id}</td>
                      <td className={styles.colType}>
                        {INQUIRY_TYPE_LABELS[it.inquiry_type]}
                      </td>
                      <td className={styles.colSubject}>
                        <Link
                          href={`/my/inquiries/${it.id}`}
                          className={styles.subjectLink}
                        >
                          <span className={styles.subjectText}>
                            {it.subject}
                          </span>
                          {it.has_attachments ? (
                            <span
                              className={styles.attachIcon}
                              aria-label="첨부 있음"
                              title="첨부 이미지 있음"
                            >
                              📎
                            </span>
                          ) : null}
                          {it.reply_count > 0 ? (
                            <span
                              className={styles.replyBadge}
                              aria-label={`답변 ${it.reply_count}건`}
                            >
                              답변 {it.reply_count}
                            </span>
                          ) : null}
                        </Link>
                      </td>
                      <td className={styles.colStatus}>
                        <InquiryStatusBadge status={it.status} />
                      </td>
                      <td className={styles.colDate}>
                        {formatDateTime(it.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <nav className={styles.pagination} aria-label="페이지 네비게이션">
                <Button
                  variant="outlined"
                  color="assistive"
                  size="small"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                >
                  이전
                </Button>
                <span className={styles.pageLabel} aria-live="polite">
                  {page} / {totalPages}
                </span>
                <Button
                  variant="outlined"
                  color="assistive"
                  size="small"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                >
                  다음
                </Button>
              </nav>
            </>
          )}
        </section>
      </main>
      <Footer />
    </>
  );
}
