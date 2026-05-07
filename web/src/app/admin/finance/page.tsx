"use client";

import Link from "next/link";
import { ComingSoonWidget } from "@/features/admin-dashboard/components/ComingSoonWidget";
import { DashboardWidget } from "@/features/admin-dashboard/components/DashboardWidget";
import styles from "./page.module.css";

export default function FinanceHubPage() {
  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>재무</h1>
        <p className={styles.caption}>
          결제 기록·예산 경고·환불 검토를 한곳에서 확인합니다. 각 카드에서 세부
          화면으로 이동할 수 있습니다.
        </p>
      </header>

      <div className={styles.cardGrid}>
        <DashboardWidget
          title="결제 기록"
          caption="결제·환불·PG 에러 이벤트 통합 타임라인"
          detailHref="/admin/finance/payments"
          detailLabel="조회 시작"
        >
          <p className={styles.cardDesc}>
            모든 사용자의 결제 성공·실패·환불·PG 에러 이벤트를 일자별 타임라인으로
            조회하고, 행 클릭 시 PG 응답 원본 JSON과 결제 상세를 펼쳐볼 수 있습니다.
            엑셀 다운로드와 에러 코드 필터를 지원합니다.
          </p>
          <p className={styles.cardMeta}>
            <Link href="/admin/finance/payments" className={styles.cardLink}>
              /admin/finance/payments →
            </Link>
          </p>
        </DashboardWidget>

        <DashboardWidget
          title="매출 대시보드"
          caption="월매출·토큰 비용·차액·에러 요약"
          detailHref="/admin/finance/revenue"
          detailLabel="조회 시작"
        >
          <p className={styles.cardDesc}>
            당월 매출(원)과 입·출력 토큰 비용을 KRW로 환산해 차액을 한눈에
            확인합니다. 월별 12개월 추이 차트와 엑셀 다운로드를 지원합니다.
          </p>
          <p className={styles.cardMeta}>
            <Link href="/admin/finance/revenue" className={styles.cardLink}>
              /admin/finance/revenue →
            </Link>
          </p>
        </DashboardWidget>

        <ComingSoonWidget
          title="예산 경고·킬스위치"
          description="월간 예산 초과 시 자동 알림과 결제 일시 정지 컨트롤. Story 9.2에서 활성화됩니다."
          storyRef="Story 9.2 — 예산 자동/수동 킬스위치"
          placeholderHint="예산 게이지 + 킬스위치 토글이 여기에 표시됩니다."
          detailDisabledTitle="Story 9.2 진행 후 공개됩니다"
        />

        <DashboardWidget
          title="고객문의·환불 검토"
          caption="문의 답변 + 수동 환불 큐 검토 (CS 탭)"
          detailHref="/admin/cs?tab=refunds"
          detailLabel="검토 시작"
        >
          <p className={styles.cardDesc}>
            사용자 고객문의에 대한 서식 답변(Tiptap)과 자동 환불 분기에서 검토 대기 중인
            환불 요청을 한 화면에서 처리합니다. 승인/거부 시 사용자에게 알림톡과
            쪽지함 통지가 즉시 발송됩니다.
          </p>
          <p className={styles.cardMeta}>
            <Link href="/admin/cs?tab=refunds" className={styles.cardLink}>
              /admin/cs →
            </Link>
          </p>
        </DashboardWidget>
      </div>
    </section>
  );
}
