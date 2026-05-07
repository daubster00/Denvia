import { TopNav } from "@/components/layout/TopNav";
import { Footer } from "@/components/layout/Footer";
import styles from "./blocked.module.css";

/**
 * 차단 사용자 페이지 — FR45.
 * 구체 사유 비공개: "이용이 제한되었습니다" 카피만 표시.
 */
export default function BlockedPage() {
  return (
    <>
      <TopNav />
      <main className={styles.main}>
        <div className={styles.card}>
          <span className={styles.icon} role="img" aria-label="이용 제한">🚫</span>
          <h1 className={styles.title}>이용이 제한되었습니다</h1>
          <p className={styles.body}>
            현재 계정의 서비스 이용이 제한되어 있습니다.
            <br />
            문의 사항이 있으시면 고객센터로 연락해주세요.
          </p>
        </div>
      </main>
      <Footer />
    </>
  );
}
