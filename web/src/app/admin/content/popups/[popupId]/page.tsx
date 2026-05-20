"use client";

import { use } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { PopupEditForm } from "@/features/admin-content/components/PopupEditForm";
import styles from "../detail.module.css";

interface PageProps {
  params: Promise<{ popupId: string }>;
}

function parsePopupId(raw: string): number | null {
  if (!/^\d+$/.test(raw)) return null;
  const n = Number(raw);
  return Number.isInteger(n) && n >= 1 ? n : null;
}

export default function AdminPopupDetailPage({ params }: PageProps) {
  const { popupId: popupIdRaw } = use(params);
  const popupId = parsePopupId(popupIdRaw);
  const router = useRouter();
  const queryClient = useQueryClient();

  if (popupId === null) {
    return (
      <section className={styles.page}>
        <div className={styles.breadcrumb}>
          <Link href="/admin/content/popups" className={styles.backLink}>
            ← 팝업 관리
          </Link>
        </div>
        <div className={styles.invalidBox} role="alert">
          잘못된 팝업 ID입니다.
        </div>
      </section>
    );
  }

  return (
    <section className={styles.page} aria-labelledby="admin-popup-edit-title">
      <div className={styles.breadcrumb}>
        <Link href="/admin/content/popups" className={styles.backLink}>
          ← 팝업 관리
        </Link>
      </div>

      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <h1 id="admin-popup-edit-title" className={styles.title}>
            팝업 편집
          </h1>
          <p className={styles.caption}>
            저장하면 목록과 사용자 노출에 즉시 반영됩니다.
          </p>
        </div>
      </header>

      <PopupEditForm
        mode="edit"
        popupId={popupId}
        onCancel={() => router.push("/admin/content/popups")}
        onSaved={() => {
          queryClient.invalidateQueries({ queryKey: ["admin", "popups"] });
          router.push("/admin/content/popups");
        }}
      />
    </section>
  );
}
