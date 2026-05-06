"use client";

import { sanitizeNoticeHtml } from "@/lib/sanitize";
import styles from "./PopupPreviewCard.module.css";

interface Props {
  title: string;
  bodyHtml: string;
  linkUrl?: string | null;
}

const SAFE_HREF_RX = /^https?:\/\//i;

/** UX-DR16 NoticeCard 스타일 라이브 프리뷰. */
export function PopupPreviewCard({ title, bodyHtml, linkUrl }: Props) {
  const safe = sanitizeNoticeHtml(bodyHtml);
  // 입력 중인 link_url을 그대로 href로 쓰면 javascript:/data:가 잠시 렌더되어
  // 미리보기 링크 클릭 시 XSS 가능. http(s)만 통과시키고 그 외에는 비활성 표시.
  const safeHref =
    linkUrl && SAFE_HREF_RX.test(linkUrl) ? linkUrl : null;
  return (
    <div className={styles.card} aria-label="팝업 미리보기">
      <h3 className={styles.title}>{title || "(제목 미입력)"}</h3>
      <div
        className={styles.body}
        // 서버에서 nh3, 클라이언트에서 DOMPurify 두 번 거른 HTML.
        dangerouslySetInnerHTML={{ __html: safe }}
      />
      {safeHref ? (
        <a
          className={styles.link}
          href={safeHref}
          target="_blank"
          rel="noopener noreferrer"
        >
          자세히 보기 →
        </a>
      ) : null}
    </div>
  );
}
