"use client";

/**
 * 마이페이지 회원정보 — 메인 클라이언트 컴포넌트.
 *
 * 섹션 구성:
 *   1) 계정정보  : 이메일(읽기 전용) + 비밀번호(설정 또는 변경)
 *   2) 연락처    : 휴대폰 (SMS 인증 후 변경)
 *   3) 기본정보  : 이름 + 주소 (다음 우편번호)
 *
 * 세션 가드는 /my/page.tsx와 동일 패턴(react-query ["session"] + useSessionStore).
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { TopNav } from "@/components/layout/TopNav";
import { Footer } from "@/components/layout/Footer";
import { useSessionStore } from "@/stores/session-store";
import { useToastStore } from "@/stores/toast-store";
import { ApiError } from "@/types/api";
import authForm from "@/styles/auth-forms.module.css";

import { useProfile } from "@/features/profile/hooks/useProfile";
import {
  updateProfile,
  type Gender,
  type ProfileResponse,
  type ProfileUpdatePayload,
} from "@/features/profile/api";
import { PasswordChangeModal } from "@/features/profile/PasswordChangeModal";
import { SetInitialPasswordModal } from "@/features/profile/SetInitialPasswordModal";
import { PhoneChangeSection } from "@/features/profile/PhoneChangeSection";
import { AddressLookupField } from "@/features/profile/AddressLookupField";

import styles from "./page.module.css";

function formatPhone(digits: string | null): string {
  if (!digits) return "(미등록)";
  const d = digits.replace(/\D/g, "");
  if (d.length !== 11) return digits;
  return `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7)}`;
}

const SEGMENT_LABEL_KO: Record<NonNullable<ProfileResponse["segment"]>, string> = {
  doctor: "치과의사",
  hygienist: "치과위생사",
  student_other: "학생·기타",
};

export function ProfileClient() {
  const router = useRouter();
  const user = useSessionStore((s) => s.user);
  const openPopup = useSessionStore((s) => s.openPopup);

  const { data, isLoading, isError } = useProfile();

  useEffect(() => {
    if (!isLoading && isError && user == null) {
      openPopup("email");
      router.replace("/?login=required");
    }
  }, [isLoading, isError, user, openPopup, router]);

  if (isLoading || !data) {
    return (
      <>
        <TopNav />
        <main className={styles.container}>
          <p className={styles.loading}>불러오는 중...</p>
        </main>
        <Footer />
      </>
    );
  }

  return <ProfileForm profile={data} />;
}

function ProfileForm({ profile }: { profile: ProfileResponse }) {
  const showToast = useToastStore((s) => s.show);
  const qc = useQueryClient();

  const [name, setName] = useState(profile.name ?? "");
  const [postcode, setPostcode] = useState(profile.postcode ?? "");
  const [addressRoad, setAddressRoad] = useState(profile.address_road ?? "");
  const [addressDetail, setAddressDetail] = useState(profile.address_detail ?? "");
  const [gender, setGender] = useState<Gender | "">(profile.gender ?? "");
  const [birthdate, setBirthdate] = useState(profile.birthdate ?? "");
  const [pwChangeOpen, setPwChangeOpen] = useState(false);
  const [pwInitOpen, setPwInitOpen] = useState(false);

  const basicInfoMutation = useMutation({
    mutationFn: (payload: ProfileUpdatePayload) => updateProfile(payload),
    onSuccess: () => {
      showToast("회원정보가 저장되었습니다.", 3000);
      qc.invalidateQueries({ queryKey: ["profile"] });
    },
    onError: (e) => {
      const msg = e instanceof ApiError ? e.message : "저장에 실패했습니다.";
      showToast(msg, 4000);
    },
  });

  const marketingMutation = useMutation({
    mutationFn: (next: boolean) => updateProfile({ marketing_consent: next }),
    onSuccess: (_data, next) => {
      showToast(
        next
          ? "마케팅 정보 수신에 동의하였습니다."
          : "마케팅 정보 수신 동의를 철회하였습니다.",
        3000,
      );
      qc.invalidateQueries({ queryKey: ["profile"] });
    },
    onError: (e) => {
      const msg = e instanceof ApiError ? e.message : "저장에 실패했습니다.";
      showToast(msg, 4000);
    },
  });

  const dirty =
    name !== (profile.name ?? "") ||
    postcode !== (profile.postcode ?? "") ||
    addressRoad !== (profile.address_road ?? "") ||
    addressDetail !== (profile.address_detail ?? "") ||
    gender !== (profile.gender ?? "") ||
    birthdate !== (profile.birthdate ?? "");

  const handleSaveBasic = () => {
    const payload: ProfileUpdatePayload = {};
    if (name !== (profile.name ?? "")) payload.name = name;
    if (postcode !== (profile.postcode ?? "")) payload.postcode = postcode;
    if (addressRoad !== (profile.address_road ?? "")) payload.address_road = addressRoad;
    if (addressDetail !== (profile.address_detail ?? "")) {
      payload.address_detail = addressDetail;
    }
    if (gender !== (profile.gender ?? "")) {
      payload.gender = gender === "" ? null : gender;
    }
    if (birthdate !== (profile.birthdate ?? "")) {
      payload.birthdate = birthdate === "" ? null : birthdate;
    }
    basicInfoMutation.mutate(payload);
  };

  return (
    <>
      <TopNav />
      <main className={styles.container}>
        <header className={styles.header}>
          <h1 className={styles.heading}>회원정보</h1>
          <p className={styles.lead}>
            계정 식별 정보와 연락처, 기본정보를 확인하고 수정할 수 있습니다.
          </p>
        </header>

        {/* 1) 계정정보 — 이메일(읽기 전용) + 비밀번호 */}
        <section className={styles.card} aria-labelledby="account-info-heading">
          <h2 id="account-info-heading" className={styles.cardHeading}>
            계정정보
          </h2>

          <div className={styles.row}>
            <span className={styles.fieldLabel}>이메일 (계정 아이디)</span>
            <div className={styles.readonlyValue}>{profile.email}</div>
            <p className={styles.cardHelp}>이메일은 변경할 수 없습니다.</p>
          </div>

          <div className={styles.row}>
            <span className={styles.fieldLabel}>비밀번호</span>
            <div className={styles.passwordRow}>
              {profile.is_social ? (
                <>
                  <span className={styles.passwordStatus}>
                    아직 비밀번호가 설정되지 않았습니다. 설정하면 이메일/비밀번호로도
                    로그인할 수 있습니다.
                  </span>
                  <button
                    type="button"
                    className={styles.passwordBtn}
                    onClick={() => setPwInitOpen(true)}
                  >
                    비밀번호 등록
                  </button>
                </>
              ) : (
                <>
                  <span className={styles.passwordStatus}>
                    비밀번호가 설정되어 있습니다.
                  </span>
                  <button
                    type="button"
                    className={styles.passwordBtn}
                    onClick={() => setPwChangeOpen(true)}
                  >
                    비밀번호 변경
                  </button>
                </>
              )}
            </div>
          </div>
        </section>

        {/* 2) 연락처 — 휴대폰 (SMS 인증 후 변경) */}
        <section className={styles.card} aria-labelledby="contact-heading">
          <h2 id="contact-heading" className={styles.cardHeading}>
            연락처
          </h2>
          <p className={styles.cardHelp}>
            현재 등록된 번호: <strong>{formatPhone(profile.phone)}</strong>
            {profile.phone_verified && " (인증됨)"}
          </p>
          <PhoneChangeSection currentPhone={profile.phone} />
        </section>

        {/* 3) 기본정보 — 이름 + 주소 */}
        <section className={styles.card} aria-labelledby="basic-info-heading">
          <h2 id="basic-info-heading" className={styles.cardHeading}>
            기본정보
          </h2>

          <div className={styles.row}>
            <label htmlFor="profile-name" className={styles.fieldLabel}>
              이름
            </label>
            <input
              id="profile-name"
              type="text"
              className={authForm.input}
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={50}
              autoComplete="name"
            />
          </div>

          <div className={styles.row}>
            <span className={styles.fieldLabel}>성별 (선택)</span>
            <div className={styles.radioGroup} role="radiogroup" aria-label="성별">
              <label className={styles.radioOption}>
                <input
                  type="radio"
                  name="profile-gender"
                  value="male"
                  checked={gender === "male"}
                  onChange={() => setGender("male")}
                />
                <span>남</span>
              </label>
              <label className={styles.radioOption}>
                <input
                  type="radio"
                  name="profile-gender"
                  value="female"
                  checked={gender === "female"}
                  onChange={() => setGender("female")}
                />
                <span>여</span>
              </label>
              {gender !== "" && (
                <button
                  type="button"
                  className={styles.linkBtn}
                  onClick={() => setGender("")}
                >
                  선택 해제
                </button>
              )}
            </div>
          </div>

          <div className={styles.row}>
            <label htmlFor="profile-birthdate" className={styles.fieldLabel}>
              생년월일 (선택)
            </label>
            <input
              id="profile-birthdate"
              type="date"
              className={authForm.input}
              value={birthdate}
              onChange={(e) => setBirthdate(e.target.value)}
              max={new Date().toISOString().slice(0, 10)}
              min="1900-01-01"
            />
          </div>

          <AddressLookupField
            value={{
              postcode,
              address_road: addressRoad,
              address_detail: addressDetail,
            }}
            onChange={(next) => {
              setPostcode(next.postcode);
              setAddressRoad(next.address_road);
              setAddressDetail(next.address_detail);
            }}
          />

          <div className={styles.saveRow}>
            <button
              type="button"
              className={styles.saveBtn}
              onClick={handleSaveBasic}
              disabled={!dirty || basicInfoMutation.isPending}
            >
              {basicInfoMutation.isPending ? "저장 중..." : "기본정보 저장"}
            </button>
          </div>
        </section>

        {/* 4) 가입유형 — 읽기 전용. 변경은 관리자만(AR34). */}
        {profile.segment !== null && (
          <section className={styles.card} aria-labelledby="segment-info-heading">
            <h2 id="segment-info-heading" className={styles.cardHeading}>
              가입유형
            </h2>
            <div className={styles.row}>
              <span className={styles.fieldLabel}>구분</span>
              <div className={styles.readonlyValue}>
                {SEGMENT_LABEL_KO[profile.segment]}
              </div>
            </div>
            {profile.segment !== "student_other" && (
              <div className={styles.row}>
                <span className={styles.fieldLabel}>연차</span>
                <div className={styles.readonlyValue}>
                  {profile.years_of_experience !== null
                    ? `${profile.years_of_experience}년차`
                    : "—"}
                </div>
              </div>
            )}
            <p className={styles.cardHelp}>
              가입유형·연차는 수정할 수 없습니다. 변경이 필요하면 우측 하단
              문의하기로 요청해주세요.
            </p>
          </section>
        )}

        {/* 5) 마케팅 정보 수신 동의 — 동의/미동의 라디오 명시 선택(알림톡·SMS 통합). */}
        <section className={styles.card} aria-labelledby="marketing-heading">
          <h2 id="marketing-heading" className={styles.cardHeading}>
            마케팅 정보 수신 동의
          </h2>
          <p className={styles.cardHelp}>
            이벤트·혜택·서비스 안내를 알림톡·SMS로 받아보실 수 있습니다.
            선택 사항이며 언제든 변경할 수 있습니다.
          </p>
          <div
            className={styles.radioGroup}
            role="radiogroup"
            aria-label="마케팅 정보 수신 동의"
          >
            <label className={styles.radioOption}>
              <input
                type="radio"
                name="profile-marketing"
                value="agree"
                checked={profile.marketing_consent === true}
                disabled={marketingMutation.isPending}
                onChange={() => marketingMutation.mutate(true)}
              />
              <span>동의함</span>
            </label>
            <label className={styles.radioOption}>
              <input
                type="radio"
                name="profile-marketing"
                value="disagree"
                checked={profile.marketing_consent === false}
                disabled={marketingMutation.isPending}
                onChange={() => marketingMutation.mutate(false)}
              />
              <span>동의하지 않음</span>
            </label>
          </div>
          {profile.marketing_consent && profile.marketing_consent_at && (
            <p className={styles.cardHelp}>
              동의일:{" "}
              {new Date(profile.marketing_consent_at).toLocaleDateString("ko-KR")}
            </p>
          )}
        </section>

        {/* 6) 약관 — 가입 시 동의한 약관 본문을 새 창에서 확인. */}
        <section className={styles.card} aria-labelledby="legal-heading">
          <h2 id="legal-heading" className={styles.cardHeading}>
            약관
          </h2>
          <p className={styles.cardHelp}>
            가입 시 동의한 약관입니다. 클릭하면 새 창에서 확인할 수 있습니다.
          </p>
          <ul className={styles.legalList}>
            <li>
              <Link
                href="/legal/terms"
                target="_blank"
                rel="noopener noreferrer"
                className={styles.legalLink}
              >
                이용약관
              </Link>
            </li>
            <li>
              <Link
                href="/legal/privacy"
                target="_blank"
                rel="noopener noreferrer"
                className={styles.legalLink}
              >
                개인정보 처리방침
              </Link>
            </li>
          </ul>
        </section>
      </main>
      <Footer />

      <PasswordChangeModal
        open={pwChangeOpen}
        onClose={() => setPwChangeOpen(false)}
      />
      <SetInitialPasswordModal
        open={pwInitOpen}
        onClose={() => setPwInitOpen(false)}
      />
    </>
  );
}
