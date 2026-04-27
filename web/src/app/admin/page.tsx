import styles from "./admin.module.css";

export default function AdminDashboardPage() {
  return (
    <div className={styles.dashboardPage}>
      <h1 className={styles.dashboardTitle}>관리자 대시보드</h1>
      <p className={styles.dashboardCaption}>
        대시보드 위젯은 Story 5.2에서 구현됩니다.
      </p>
    </div>
  );
}
