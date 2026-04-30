"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAdminEventsStore } from "@/stores/admin-events-store";
import { cancelRebuild } from "@/features/admin-rag/api/knowledge";
import { ConfirmDialog } from "@/components/layout/ConfirmDialog";
import styles from "./RebuildBanner.module.css";

export function RebuildBanner() {
  const queryClient = useQueryClient();
  const { rebuildProgress, activeJobId, setRebuildProgress, setActiveJobId, setLastCompletedJobId } =
    useAdminEventsStore();
  const [hidden, setHidden] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  useEffect(() => {
    if (sessionStorage.getItem("rebuild_banner_hidden") === "1") setHidden(true);
  }, []);

  useEffect(() => {
    if (!rebuildProgress) return;
    if (rebuildProgress.progress === 100 && rebuildProgress.status === "success") {
      setToastMsg("✅ 재빌드 완료");
      setLastCompletedJobId(rebuildProgress.job_id);
      setRebuildProgress(null);
      setActiveJobId(null);
      setHidden(false);
      sessionStorage.removeItem("rebuild_banner_hidden");
      queryClient.invalidateQueries({ queryKey: ["admin-rag-status"] });
      queryClient.invalidateQueries({ queryKey: ["admin-rag-knowledge"] });
    } else if (rebuildProgress.stage === "failed") {
      setToastMsg(`❌ 재빌드 실패: ${rebuildProgress.error ?? "알 수 없음"}`);
      setLastCompletedJobId(rebuildProgress.job_id);
      setRebuildProgress(null);
      setActiveJobId(null);
      setHidden(false);
      sessionStorage.removeItem("rebuild_banner_hidden");
      queryClient.invalidateQueries({ queryKey: ["admin-rag-status"] });
    }
  }, [rebuildProgress, setRebuildProgress, setActiveJobId, setLastCompletedJobId, queryClient]);

  useEffect(() => {
    if (!toastMsg) return;
    const t = setTimeout(() => setToastMsg(null), 5000);
    return () => clearTimeout(t);
  }, [toastMsg]);

  const handleShow = () => {
    setHidden(false);
    sessionStorage.removeItem("rebuild_banner_hidden");
  };

  if (!rebuildProgress || hidden) {
    return (
      <>
        {hidden && rebuildProgress && (
          <button
            type="button"
            onClick={handleShow}
            className={styles.restoreChip}
            aria-label="재빌드 진행 배너 다시 보기"
          >
            🔄 재빌드 {rebuildProgress.progress}% · 다시 보기
          </button>
        )}
        {toastMsg && (
          <div role="alert" className={styles.toast}>
            {toastMsg}
          </div>
        )}
      </>
    );
  }

  const handleHide = () => {
    setHidden(true);
    sessionStorage.setItem("rebuild_banner_hidden", "1");
  };

  const handleCancel = async () => {
    if (!activeJobId) return;
    try {
      await cancelRebuild(activeJobId);
    } catch {
      // 취소 실패는 무시하고 UI 닫기
    }
    setConfirmCancel(false);
    setLastCompletedJobId(activeJobId);
    setRebuildProgress(null);
    setActiveJobId(null);
    sessionStorage.removeItem("rebuild_banner_hidden");
  };

  return (
    <>
      <div
        role="status"
        aria-live="polite"
        className={styles.banner}
        style={{ "--progress": `${rebuildProgress.progress}%` } as React.CSSProperties}
      >
        <span className={styles.icon}>🔄</span>
        <span className={styles.msg}>
          벡터스토어 재빌드 중 ({rebuildProgress.progress}%) · {rebuildProgress.stage} stage
        </span>
        <div className={styles.progressBar} />
        <button
          type="button"
          onClick={() => setConfirmCancel(true)}
          className={styles.cancelBtn}
        >
          취소
        </button>
        <button type="button" onClick={handleHide} className={styles.hideBtn}>
          숨기기
        </button>
      </div>
      <ConfirmDialog
        open={confirmCancel}
        title="재빌드를 취소하시겠습니까?"
        description="취소해도 현재 서비스는 영향받지 않습니다."
        confirmLabel="취소"
        danger
        onConfirm={handleCancel}
        onCancel={() => setConfirmCancel(false)}
      />
      {toastMsg && (
        <div role="alert" className={styles.toast}>
          {toastMsg}
        </div>
      )}
    </>
  );
}
