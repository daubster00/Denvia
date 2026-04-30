"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { IndexStatusCard } from "@/features/admin-rag/components/IndexStatusCard";
import { UploadDropzone } from "@/features/admin-rag/components/UploadDropzone";
import { KnowledgeFileTable } from "@/features/admin-rag/components/KnowledgeFileTable";
import { HierarchyPreviewDrawer } from "@/features/admin-rag/components/HierarchyPreviewDrawer";
import { KnowledgeFileEditDialog } from "@/features/admin-rag/components/KnowledgeFileEditDialog";
import { ConfirmDialog } from "@/components/layout/ConfirmDialog";
import {
  KnowledgeListItem,
  UploadKnowledgeResponse,
  deleteKnowledge,
  fetchRagStatus,
  triggerRebuild,
} from "@/features/admin-rag/api/knowledge";
import { useAdminEventsStore } from "@/stores/admin-events-store";
import styles from "./page.module.css";

// 서버는 0/10/20/80/95/100 단계에서만 progress 이벤트를 보낸다.
// 20→80 구간은 임베딩이 도는 긴 구간이라 게이지가 멈춰 보이므로,
// 단계 사이를 다음 마일스톤 직전까지 클라이언트가 자연스럽게 채워 올린다.
function ceilingFor(actual: number): number {
  if (actual >= 100) return 100;
  if (actual >= 95) return 99;
  if (actual >= 80) return 94;
  if (actual >= 20) return 78;
  if (actual >= 10) return 19;
  return 9;
}

function useSmoothedRebuildProgress(actualPercent: number, isActive: boolean): number {
  const [display, setDisplay] = useState(0);
  const lastActualRef = useRef(0);

  useEffect(() => {
    if (!isActive) {
      setDisplay(0);
      lastActualRef.current = 0;
    }
  }, [isActive]);

  useEffect(() => {
    if (!isActive) return;
    if (actualPercent > lastActualRef.current) {
      lastActualRef.current = actualPercent;
      setDisplay((prev) => Math.max(prev, actualPercent));
    }
  }, [actualPercent, isActive]);

  useEffect(() => {
    if (!isActive) return;
    const id = setInterval(() => {
      setDisplay((prev) => {
        const ceiling = ceilingFor(lastActualRef.current);
        if (prev >= ceiling) return prev;
        const step = Math.max(0.4, (ceiling - prev) * 0.05);
        return Math.min(ceiling, prev + step);
      });
    }, 350);
    return () => clearInterval(id);
  }, [isActive]);

  return Math.round(display);
}

export default function AdminRagDataPage() {
  const queryClient = useQueryClient();
  const [refreshSignal, setRefreshSignal] = useState(0);
  const [highlightId, setHighlightId] = useState<number | undefined>();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [uploadResp, setUploadResp] = useState<UploadKnowledgeResponse | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [deletingItem, setDeletingItem] = useState<KnowledgeListItem | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteSuccessMsg, setDeleteSuccessMsg] = useState<string | null>(null);

  const { data: ragStatus } = useQuery({
    queryKey: ["admin-rag-status"],
    queryFn: fetchRagStatus,
    staleTime: 30_000,
  });

  const {
    rebuildProgress,
    setActiveJobId,
    setRebuildProgress,
    setLastCompletedJobId,
  } = useAdminEventsStore();

  useEffect(() => {
    if (!rebuildProgress) return;
    const isTerminal =
      rebuildProgress.status === "success" ||
      rebuildProgress.status === "failed" ||
      rebuildProgress.status === "canceled";
    if (!isTerminal) return;
    queryClient.invalidateQueries({ queryKey: ["admin-rag-status"] });
    queryClient.invalidateQueries({ queryKey: ["admin-rag-knowledge"] });
    setLastCompletedJobId(rebuildProgress.job_id);
    const timer = setTimeout(() => {
      setRebuildProgress(null);
      setActiveJobId(null);
    }, 1200);
    return () => clearTimeout(timer);
  }, [rebuildProgress, queryClient, setRebuildProgress, setActiveJobId, setLastCompletedJobId]);

  const handleRebuild = async () => {
    try {
      const res = await triggerRebuild();
      setActiveJobId(res.job_id);
      queryClient.invalidateQueries({ queryKey: ["admin-rag-status"] });
    } catch (e) {
      const err = e as { code?: string; message?: string };
      if (err.code === "REBUILD_ALREADY_IN_PROGRESS") {
        alert("이미 재빌드가 진행 중입니다.");
      } else if (err.code === "REBUILD_NO_ACTIVE_FILES") {
        alert("재빌드할 활성 지식 파일이 없습니다. 새 파일을 업로드한 뒤 다시 시도해 주세요.");
      } else {
        alert(err.message ?? "재빌드 실행에 실패했습니다.");
      }
    }
  };

  const isRebuilding = !!ragStatus?.active_rebuild || !!rebuildProgress;
  const actualPercent =
    rebuildProgress?.progress ?? ragStatus?.active_rebuild?.progress_percent ?? 0;
  const progressPercent = useSmoothedRebuildProgress(actualPercent, isRebuilding);

  const handleValidatedCountChange = useCallback(() => {
    // count는 ragStatus에서 가져오므로 이 콜백은 빈 상태로 유지
  }, []);

  const handleUploadSuccess = (resp: UploadKnowledgeResponse) => {
    setUploadResp(resp);
    setDrawerOpen(true);
    setRefreshSignal((s) => s + 1);
    queryClient.invalidateQueries({ queryKey: ["admin-rag-knowledge"] });
    queryClient.invalidateQueries({ queryKey: ["admin-rag-status"] });
  };

  const handleHighlightDuplicate = (id: number) => {
    setHighlightId(id);
    setTimeout(() => setHighlightId(undefined), 3000);
  };

  const handleDrawerClose = () => {
    setDrawerOpen(false);
  };

  const handleEditSaved = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-rag-knowledge"] });
    queryClient.invalidateQueries({ queryKey: ["admin-rag-status"] });
  };

  const handleDeleteConfirm = async () => {
    if (!deletingItem) return;
    const wasIndexed = deletingItem.status === "active";
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      await deleteKnowledge(deletingItem.id);
      setDeletingItem(null);
      setDeleteSuccessMsg(
        wasIndexed
          ? "파일이 삭제됩니다. 다음 재빌드 후 검색에서 제외됩니다."
          : "파일이 삭제되었습니다."
      );
      setTimeout(() => setDeleteSuccessMsg(null), 5000);
      queryClient.invalidateQueries({ queryKey: ["admin-rag-knowledge"] });
      queryClient.invalidateQueries({ queryKey: ["admin-rag-status"] });
    } catch (e) {
      setDeleteError((e as Error).message ?? "삭제에 실패했습니다.");
    } finally {
      setDeleteLoading(false);
    }
  };

  return (
    <div className={styles.page}>
      <h1 className={styles.heading}>RAG 데이터 관리</h1>

      <section className={styles.section}>
        <IndexStatusCard
          pendingChangesCount={ragStatus?.pending_changes_count ?? 0}
          lastRebuildAt={ragStatus?.last_rebuild_at ?? null}
          lastRebuildStatus={ragStatus?.last_rebuild_status ?? null}
          isRebuilding={isRebuilding}
          rebuildProgress={progressPercent}
          onRebuild={handleRebuild}
        />
      </section>

      <section className={styles.section}>
        <h2 className={styles.subheading}>파일 업로드</h2>
        <UploadDropzone
          onSuccess={handleUploadSuccess}
          onHighlightDuplicate={handleHighlightDuplicate}
        />
      </section>

      <section className={styles.section}>
        <h2 className={styles.subheading}>업로드된 파일</h2>
        <KnowledgeFileTable
          refreshSignal={refreshSignal}
          highlightId={highlightId}
          onHighlight={setHighlightId}
          onValidatedCountChange={handleValidatedCountChange}
          onEdit={(id) => setEditingId(id)}
          onDelete={(item) => setDeletingItem(item)}
        />
      </section>

      {uploadResp && (
        <HierarchyPreviewDrawer
          open={drawerOpen}
          hierarchy={uploadResp.hierarchy_preview}
          filename={uploadResp.filename}
          chunkCount={uploadResp.chunk_count}
          onClose={handleDrawerClose}
        />
      )}

      {editingId !== null && (
        <KnowledgeFileEditDialog
          uploadId={editingId}
          onClose={() => setEditingId(null)}
          onSaved={handleEditSaved}
        />
      )}

      {deleteSuccessMsg && (
        <p role="status" className={styles.successMsg}>{deleteSuccessMsg}</p>
      )}

      <ConfirmDialog
        open={deletingItem !== null}
        title={
          deletingItem?.status === "active"
            ? "지식 파일을 삭제하시겠습니까?"
            : "업로드된 파일을 삭제하시겠습니까?"
        }
        description={
          deletingItem?.status === "active"
            ? "이 파일의 지식이 다음 재빌드 후 검색에서 제외됩니다."
            : "아직 검색에 반영되지 않은 파일입니다. 삭제하면 재빌드 대기 목록에서 제거됩니다."
        }
        confirmLabel="삭제"
        danger
        isSubmitting={deleteLoading}
        errorMessage={deleteError ?? undefined}
        onConfirm={handleDeleteConfirm}
        onCancel={() => {
          if (!deleteLoading) {
            setDeletingItem(null);
            setDeleteError(null);
          }
        }}
      />
    </div>
  );
}
