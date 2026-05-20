"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { PopupEditForm } from "@/features/admin-content/components/PopupEditForm";
import styles from "../detail.module.css";

export default function AdminPopupNewPage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  return (
    <section className={styles.page} aria-labelledby="admin-popup-new-title">
      <div className={styles.breadcrumb}>
        <Link href="/admin/content/popups" className={styles.backLink}>
          ← 팝업 관리
        </Link>
      </div>

      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <h1 id="admin-popup-new-title" className={styles.title}>
            새 팝업 작성
          </h1>
          <p className={styles.caption}>
            노출 기간·타겟·디바이스를 정한 뒤 저장하면 목록에 추가됩니다.
          </p>
        </div>
      </header>

      <PopupEditForm
        mode="create"
        onCancel={() => router.push("/admin/content/popups")}
        onSaved={() => {
          queryClient.invalidateQueries({ queryKey: ["admin", "popups"] });
          router.push("/admin/content/popups");
        }}
      />
    </section>
  );
}
