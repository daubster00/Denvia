"use client";

/** 가입유형/연차 카드 — Story 4.3 AC-5 (read-only + 문의하기 안내). */

import Link from "next/link";
import { IconPersons } from "@wanteddev/wds-icon";

import styles from "./SegmentCard.module.css";

const SEGMENT_LABEL: Record<"doctor" | "hygienist" | "student_other", string> = {
  doctor: "치과의사",
  hygienist: "치과위생사",
  student_other: "학생·기타",
};

interface SegmentCardProps {
  segment: "doctor" | "hygienist" | "student_other" | null;
  yearsOfExperience: number | null;
}

export function SegmentCard({ segment, yearsOfExperience }: SegmentCardProps) {
  if (segment === null) {
    return (
      <section className={styles.card} aria-label="가입유형">
        <div className={styles.iconBox} aria-hidden="true">
          <IconPersons className={styles.icon} />
        </div>
        <div className={styles.content}>
          <h2 className={styles.title}>가입유형</h2>
          <p className={styles.placeholder}>회원 정보를 완성해주세요.</p>
          <Link href="/signup/segment" className={styles.completeLink}>
            가입유형 설정하기
          </Link>
        </div>
      </section>
    );
  }

  const showYears = segment !== "student_other" && yearsOfExperience !== null;

  return (
    <section className={styles.card} aria-label="가입유형">
      <div className={styles.iconBox} aria-hidden="true">
        <IconPersons className={styles.icon} />
      </div>
      <div className={styles.content}>
        <h2 className={styles.title}>가입유형</h2>
        <dl className={styles.fields}>
          <div className={styles.fieldRow}>
            <dt className={styles.fieldLabel}>구분</dt>
            <dd className={styles.fieldValue}>{SEGMENT_LABEL[segment]}</dd>
          </div>
          {showYears && (
            <div className={styles.fieldRow}>
              <dt className={styles.fieldLabel}>연차</dt>
              <dd className={styles.fieldValue}>{yearsOfExperience}년차</dd>
            </div>
          )}
        </dl>
        <p className={styles.caption}>
          변경은 우측 하단 문의하기를 통해 요청해주세요.
        </p>
      </div>
    </section>
  );
}
