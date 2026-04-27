"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import styles from "./FreeDelayBanner.module.css";

const BANNER_SEEN_KEY = "denvia.free_delay_banner_seen";
const AUTO_FADE_MS = 15_000;

interface FreeDelayBannerProps {
  show: boolean;
}

export function FreeDelayBanner({ show }: FreeDelayBannerProps) {
  const router = useRouter();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!show) return;
    if (typeof window === "undefined") return;
    if (localStorage.getItem(BANNER_SEEN_KEY)) return;
    setVisible(true);
    const timer = setTimeout(() => {
      setVisible(false);
      localStorage.setItem(BANNER_SEEN_KEY, "1");
    }, AUTO_FADE_MS);
    return () => clearTimeout(timer);
  }, [show]);

  function handleDismiss() {
    setVisible(false);
    localStorage.setItem(BANNER_SEEN_KEY, "1");
  }

  if (!visible) return null;

  return (
    <div role="status" className={styles.banner}>
      <span>
        무료 플랜은 응답이 조금 느려요.{" "}
        <button
          type="button"
          onClick={() => router.push("/subscribe")}
          className={styles.upgradeLink}
        >
          Pro로 즉시 답변받기 →
        </button>
      </span>
      <button
        type="button"
        aria-label="배너 닫기"
        onClick={handleDismiss}
        className={styles.dismissBtn}
      >
        ✕
      </button>
    </div>
  );
}
