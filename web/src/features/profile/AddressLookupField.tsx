"use client";

/**
 * 주소 입력 — 다음(카카오) 우편번호 검색 다이얼로그 + 상세주소 input.
 *
 * `react-daum-postcode`가 내부적으로 Daum 스크립트를 lazy-load한다.
 * 우편번호 + 도로명/지번 주소는 다이얼로그에서 자동 채우고,
 * 상세주소는 사용자가 수동 입력.
 */

import { useEffect, useState } from "react";
import DaumPostcode, { type Address } from "react-daum-postcode";

import authForm from "@/styles/auth-forms.module.css";
import styles from "./AddressLookupField.module.css";

interface AddressValue {
  postcode: string;
  address_road: string;
  address_detail: string;
}

interface Props {
  value: AddressValue;
  onChange: (next: AddressValue) => void;
  /** input id prefix — 같은 페이지에 여러 폼이 있을 때 id 충돌 회피. 기본 'profile'. */
  idPrefix?: string;
}

export function AddressLookupField({ value, onChange, idPrefix = "profile" }: Props) {
  const [open, setOpen] = useState(false);
  const postcodeId = `${idPrefix}-postcode`;
  const addressRoadId = `${idPrefix}-address-road`;
  const addressDetailId = `${idPrefix}-address-detail`;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const handleComplete = (data: Address) => {
    const road = data.roadAddress || data.jibunAddress || data.address;
    onChange({
      postcode: data.zonecode,
      address_road: road,
      address_detail: value.address_detail,
    });
    setOpen(false);
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.postcodeRow}>
        <div className={styles.postcodeInput}>
          <label htmlFor={postcodeId} className={authForm.fieldLabel}>
            우편번호
          </label>
          <input
            id={postcodeId}
            type="text"
            className={authForm.input}
            value={value.postcode}
            readOnly
            placeholder="검색"
          />
        </div>
        <button
          type="button"
          className={styles.lookupBtn}
          onClick={() => setOpen(true)}
        >
          주소 검색
        </button>
      </div>

      <div>
        <label htmlFor={addressRoadId} className={authForm.fieldLabel}>
          도로명/지번 주소
        </label>
        <input
          id={addressRoadId}
          type="text"
          className={authForm.input}
          value={value.address_road}
          readOnly
          placeholder="주소 검색을 눌러주세요"
        />
      </div>

      <div>
        <label htmlFor={addressDetailId} className={authForm.fieldLabel}>
          상세주소
        </label>
        <input
          id={addressDetailId}
          type="text"
          className={authForm.input}
          value={value.address_detail}
          onChange={(e) =>
            onChange({ ...value, address_detail: e.target.value })
          }
          placeholder="동/호수 등"
          maxLength={100}
        />
      </div>

      {open && (
        <div className={styles.dimmer} role="presentation" onClick={() => setOpen(false)}>
          <div
            className={styles.dialog}
            role="dialog"
            aria-modal="true"
            aria-label="주소 검색"
            onClick={(e) => e.stopPropagation()}
          >
            <div className={styles.dialogHeader}>
              <h2 className={styles.dialogTitle}>주소 검색</h2>
              <button
                type="button"
                className={styles.closeBtn}
                onClick={() => setOpen(false)}
                aria-label="닫기"
              >
                ✕
              </button>
            </div>
            <div className={styles.postcodeFrame}>
              <DaumPostcode onComplete={handleComplete} autoClose={false} style={{ height: "100%" }} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
