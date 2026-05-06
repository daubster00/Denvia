"use client";

import Link from "next/link";
import styles from "./page.module.css";

const FINANCE_ITEMS = [
  {
    href: "/admin/dashboard/budget",
    title: "월 예산 모니터링",
    description: "당월 토큰 비용·예산 소진율·킬스위치 상태를 확인합니다.",
  },
  {
    href: "/admin/dashboard/token-breakdown",
    title: "사용자별 토큰 사용",
    description: "기간별 사용자 토큰 소비량과 비용 상위 목록을 조회합니다.",
  },
];

export default function FinancePage() {
  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>재무</h1>
        <p className={styles.caption}>예산 및 토큰 비용 현황을 관리합니다.</p>
      </header>

      <div className={styles.grid}>
        {FINANCE_ITEMS.map((item) => (
          <Link key={item.href} href={item.href} className={styles.card}>
            <p className={styles.cardTitle}>{item.title}</p>
            <p className={styles.cardDesc}>{item.description}</p>
            <span className={styles.cardArrow} aria-hidden="true">→</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
