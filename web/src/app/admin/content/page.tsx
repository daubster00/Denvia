"use client";

import Link from "next/link";
import { ServiceTogglesForm } from "@/features/admin-content/components/ServiceTogglesForm";
import styles from "./page.module.css";

const CONTENT_LINKS = [
  {
    href: "/admin/content/popups",
    title: "팝업 관리",
    description: "메인 화면 팝업을 작성·노출 기간 설정·활성/비활성 처리합니다.",
    enabled: true,
  },
  {
    href: "/admin/content/notices",
    title: "공지사항 관리",
    description: "전체 사용자에게 발송되는 알림글을 작성·수정합니다. (준비 중)",
    enabled: false,
  },
];

export default function AdminContentHubPage() {
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.heading}>컨텐츠 관리</h1>
        <p className={styles.subheading}>
          서비스 전체에 적용되는 토글과 콘텐츠 관리 도구를 한 곳에 모았습니다.
        </p>
      </header>

      <ServiceTogglesForm />

      <section
        className={styles.linksSection}
        aria-labelledby="content-links-heading"
      >
        <h2 id="content-links-heading" className={styles.linksHeading}>
          콘텐츠 관리 도구
        </h2>
        <div className={styles.linksGrid}>
          {CONTENT_LINKS.map((item) =>
            item.enabled ? (
              <Link
                key={item.href}
                href={item.href}
                className={styles.linkCard}
              >
                <p className={styles.linkTitle}>{item.title}</p>
                <p className={styles.linkDesc}>{item.description}</p>
                <span className={styles.linkArrow} aria-hidden="true">
                  →
                </span>
              </Link>
            ) : (
              <div
                key={item.href}
                className={`${styles.linkCard} ${styles.linkCardDisabled}`}
                aria-disabled="true"
              >
                <p className={styles.linkTitle}>{item.title}</p>
                <p className={styles.linkDesc}>{item.description}</p>
                <span className={styles.linkBadge}>준비 중</span>
              </div>
            ),
          )}
        </div>
      </section>
    </main>
  );
}
