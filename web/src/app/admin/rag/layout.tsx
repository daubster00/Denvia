"use client";

import styles from "./layout.module.css";

export default function RagLayout({ children }: { children: React.ReactNode }) {
  return <div className={styles.container}>{children}</div>;
}
