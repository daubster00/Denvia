"use client";

/** CS 섹션 내 탭 네비게이션 — 문의 / 쪽지(공지) 사이 이동. Story 7.1. */

import Link from "next/link";
import { usePathname } from "next/navigation";

import styles from "./CsTabsNav.module.css";

const TABS = [
  { href: "/admin/cs", label: "고객 문의" },
  { href: "/admin/cs/notices", label: "쪽지 관리" },
];

export function CsTabsNav() {
  const pathname = usePathname();
  return (
    <nav className={styles.tabs} aria-label="CS 하위 메뉴">
      {TABS.map((tab) => {
        const active =
          tab.href === "/admin/cs"
            ? pathname === "/admin/cs"
            : pathname === tab.href || pathname.startsWith(`${tab.href}/`);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={styles.tab}
            aria-current={active ? "page" : undefined}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
