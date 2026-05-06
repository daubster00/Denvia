"use client";

import Link from "next/link";
import styles from "./page.module.css";

const SETTINGS_ITEMS = [
  {
    href: "/admin/prompt",
    title: "프롬프트 관리",
    description: "RAG 프롬프트 모듈을 편집하고 버전을 관리합니다.",
  },
  {
    href: "/admin/rag/model",
    title: "모델 파라미터",
    description: "LLM 모델 파라미터(temperature, top_p 등)를 조정합니다.",
  },
  {
    href: "/admin/rag/data",
    title: "RAG 지식 데이터",
    description: "지식 자료 업로드·편집·재인덱스를 수행합니다.",
  },
  {
    href: "/admin/dashboard/budget",
    title: "월 예산 / 킬스위치",
    description: "월 토큰 비용·소진율·자동 차단(killswitch) 상태를 관리합니다.",
  },
];

export default function SettingsPage() {
  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>설정</h1>
        <p className={styles.caption}>
          서비스 운영 설정으로 이동합니다. 각 항목은 별도 화면에서 편집할 수 있습니다.
        </p>
      </header>

      <div className={styles.grid}>
        {SETTINGS_ITEMS.map((item) => (
          <Link key={item.href} href={item.href} className={styles.card}>
            <p className={styles.cardTitle}>{item.title}</p>
            <p className={styles.cardDesc}>{item.description}</p>
            <span className={styles.cardArrow} aria-hidden="true">
              →
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
