"use client";

import type { PopupListItem, TargetSegment } from "@/features/admin-content/api/popup";
import styles from "./PopupListTable.module.css";

interface Props {
  items: PopupListItem[];
  togglingId: number | null;
  onEdit: (id: number) => void;
  onToggle: (id: number, nextActive: boolean) => void;
  onDelete: (item: PopupListItem) => void;
}

const SEGMENT_LABEL: Record<TargetSegment, string> = {
  all: "전체",
  doctor: "의사",
  hygienist: "위생사",
  student_other: "학생·기타",
};

const SEGMENT_CLASS: Record<TargetSegment, string> = {
  all: styles.segmentAll,
  doctor: styles.segmentDoctor,
  hygienist: styles.segmentHygienist,
  student_other: styles.segmentStudentOther,
};

// 서비스가 단일 리전(KST) 운영이라 노출 시간은 항상 KST로 표기.
// 관리자 브라우저 타임존이 다르더라도 동일하게 보이도록 Asia/Seoul로 강제.
const KST_FORMATTER = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function formatRange(startIso: string, endIso: string): string {
  const fmt = (iso: string) => {
    const parts = KST_FORMATTER.formatToParts(new Date(iso));
    const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
    return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get(
      "minute",
    )}`;
  };
  return `${fmt(startIso)} ~ ${fmt(endIso)} (KST)`;
}

export function PopupListTable({
  items,
  togglingId,
  onEdit,
  onToggle,
  onDelete,
}: Props) {
  if (items.length === 0) {
    return (
      <p className={styles.empty} role="status">
        등록된 팝업이 없습니다. 우측 상단 &quot;새 팝업 작성&quot; 버튼을 눌러
        시작해보세요.
      </p>
    );
  }

  return (
    <table className={styles.table} aria-label="팝업 목록">
      <thead>
        <tr>
          <th scope="col">제목</th>
          <th scope="col">노출 기간</th>
          <th scope="col">타겟</th>
          <th scope="col">활성</th>
          <th scope="col">액션</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => {
          // 서버가 신규 segment를 추가했을 때 프론트가 미반영이어도 깨지지 않도록 fallback.
          const segmentClass =
            SEGMENT_CLASS[item.target_segment] ?? styles.segmentAll;
          const segmentLabel =
            SEGMENT_LABEL[item.target_segment] ?? item.target_segment;
          const isToggling = togglingId === item.id;
          return (
            <tr key={item.id}>
              <td className={styles.titleCell}>{item.title}</td>
              <td>{formatRange(item.display_start, item.display_end)}</td>
              <td>
                <span className={`${styles.segmentBadge} ${segmentClass}`}>
                  {segmentLabel}
                </span>
              </td>
              <td>
                <button
                  type="button"
                  role="switch"
                  aria-checked={item.is_active}
                  aria-label={`${item.title} 활성화 토글`}
                  disabled={isToggling}
                  onClick={() => onToggle(item.id, !item.is_active)}
                  className={
                    item.is_active ? styles.switchOn : styles.switchOff
                  }
                >
                  {item.is_active ? "ON" : "OFF"}
                </button>
              </td>
              <td className={styles.actionsCell}>
                <button
                  type="button"
                  className={styles.editBtn}
                  onClick={() => onEdit(item.id)}
                >
                  편집
                </button>
                <button
                  type="button"
                  className={styles.deleteBtn}
                  onClick={() => onDelete(item)}
                >
                  삭제
                </button>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
