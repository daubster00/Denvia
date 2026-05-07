"use client";

import { useCallback } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { InquiriesTabPanel } from "@/features/admin-support/components/InquiriesTabPanel";
import { RefundsTabPanel } from "@/features/admin-support/components/RefundsTabPanel";
import {
  SupportTabsNav,
  type SupportTabKey,
} from "@/features/admin-support/components/SupportTabsNav";
import { useSupportCounts } from "@/features/admin-support/hooks/useSupportCounts";
import styles from "./page.module.css";

const VALID_TABS: SupportTabKey[] = ["inquiries", "refunds"];

function parseTab(raw: string | null): SupportTabKey {
  if (raw && (VALID_TABS as string[]).includes(raw)) {
    return raw as SupportTabKey;
  }
  return "inquiries";
}

export default function CsPage() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const tab = parseTab(sp.get("tab"));

  const counts = useSupportCounts();

  const setTab = useCallback(
    (next: SupportTabKey) => {
      const params = new URLSearchParams(sp.toString());
      params.set("tab", next);
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [sp, router, pathname],
  );

  return (
    <section className={styles.page} aria-labelledby="admin-cs-title">
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <h1 id="admin-cs-title" className={styles.title}>
            CS
          </h1>
          <p className={styles.caption}>
            고객 문의와 환불 요청을 검토·응답합니다. 답변과 환불 처리는 사용자에게
            알림톡과 쪽지함으로 즉시 발송됩니다.
          </p>
        </div>
      </header>

      <SupportTabsNav
        activeTab={tab}
        onChange={setTab}
        inquiryCount={counts.data?.open_inquiries ?? 0}
        refundCount={counts.data?.pending_refunds ?? 0}
      />

      {tab === "inquiries" ? <InquiriesTabPanel /> : <RefundsTabPanel />}
    </section>
  );
}
