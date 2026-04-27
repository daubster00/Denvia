"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import {
  IconApps,
  IconPersons,
  IconCircleBlock,
  IconDocument,
  IconStorage,
  IconCode,
  IconCoins,
  IconBubble,
  IconSetting,
  IconChevronRight,
} from "@wanteddev/wds-icon";

interface MenuItem {
  icon: React.ComponentType<{ size?: number; color?: string }>;
  label: string;
  href: string;
}

const MENU_ITEMS: MenuItem[] = [
  { icon: IconApps, label: "대시보드", href: "/admin" },
  { icon: IconPersons, label: "고객관리", href: "/admin/users" },
  { icon: IconCircleBlock, label: "이상탐지", href: "/admin/anomaly" },
  { icon: IconDocument, label: "콘텐츠", href: "/admin/content" },
  { icon: IconStorage, label: "RAG 데이터", href: "/admin/rag" },
  { icon: IconCode, label: "프롬프트", href: "/admin/prompt" },
  { icon: IconCoins, label: "재무", href: "/admin/finance" },
  { icon: IconBubble, label: "CS", href: "/admin/cs" },
  { icon: IconSetting, label: "설정", href: "/admin/settings" },
];

export function AdminSidebar() {
  const pathname = usePathname();
  const [isTabletExpanded, setIsTabletExpanded] = useState(false);

  const isActive = (href: string) =>
    href === "/admin" ? pathname === "/admin" : pathname.startsWith(href);

  return (
    <>
      {/* 태블릿 오버레이 */}
      {isTabletExpanded && (
        <div
          className="fixed inset-0 z-40 bg-black/30 lg:hidden"
          onClick={() => setIsTabletExpanded(false)}
          aria-hidden="true"
        />
      )}

      <nav
        aria-label="관리자 메뉴"
        style={{
          width: isTabletExpanded ? 240 : undefined,
          position: isTabletExpanded ? "fixed" : undefined,
          top: isTabletExpanded ? 0 : undefined,
          left: isTabletExpanded ? 0 : undefined,
          bottom: isTabletExpanded ? 0 : undefined,
          zIndex: isTabletExpanded ? 50 : undefined,
        }}
        className={[
          "bg-white border-r border-gray-200 flex flex-col overflow-hidden transition-all",
          "hidden md:flex",
          "lg:w-[240px]",
          !isTabletExpanded ? "md:w-[64px]" : "md:w-[240px]",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {/* 태블릿 토글 버튼 */}
        <button
          type="button"
          className="lg:hidden p-4 flex justify-end text-gray-500 hover:text-gray-800"
          onClick={() => setIsTabletExpanded((v) => !v)}
          aria-label={isTabletExpanded ? "메뉴 닫기" : "메뉴 펼치기"}
        >
          <IconChevronRight
            size={20}
            color="currentColor"
          />
        </button>

        <ul className="flex flex-col gap-1 px-2 flex-1">
          {MENU_ITEMS.map(({ icon: Icon, label, href }) => {
            const active = isActive(href);
            const showLabel = isTabletExpanded;

            return (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={[
                    "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                    "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-500",
                    active
                      ? "bg-violet-50 text-violet-700"
                      : "text-gray-600 hover:bg-gray-100 hover:text-gray-900",
                    !showLabel ? "lg:justify-start justify-center" : "justify-start",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                >
                  <Icon
                    size={20}
                    color={active ? "#7C3AED" : "currentColor"}
                  />
                  <span
                    className={[
                      "whitespace-nowrap overflow-hidden",
                      showLabel ? "block" : "hidden lg:block",
                    ].join(" ")}
                  >
                    {label}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </>
  );
}
