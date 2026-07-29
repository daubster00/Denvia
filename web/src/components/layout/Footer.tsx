import Image from "next/image";
import Link from "next/link";
import styles from "./Footer.module.css";

const COMPANY = {
  name: "더플랜",
  representative: "이규성",
  businessNumber: "399-71-00496",
  address: "경기도 가평군 가평읍 향교로27번길 4-32, 201호(한성연립)",
  email: "denvia@naver.com",
  phone: "010-2323-2753",
};

// 사업자 정보 란(대표자·회사명·사업자등록번호 등) 노출 여부 — 게시판 #135.
// PG 심사용으로 노출했으나 토스 심사 취소·새 PG 검토 중이라 임시 숨김.
// 새 PG 선정 시 true 로 되돌리면 원상 복원된다.
const SHOW_BUSINESS_INFO = false;

export function Footer() {
  const year = new Date().getFullYear();

  return (
    <footer className={styles.footer} aria-label="사업자 정보">
      <div className={styles.inner}>
        <div className={styles.brandRow}>
          <Image
            src="/logo-full.png"
            alt="Denvia"
            width={916}
            height={269}
            className={styles.logo}
          />
        </div>

        {SHOW_BUSINESS_INFO && (
          <dl className={styles.infoGrid}>
            <div className={styles.infoItem}>
              <dt className={styles.label}>회사명</dt>
              <dd className={styles.value}>{COMPANY.name}</dd>
            </div>
            <div className={styles.infoItem}>
              <dt className={styles.label}>대표</dt>
              <dd className={styles.value}>{COMPANY.representative}</dd>
            </div>
            <div className={styles.infoItem}>
              <dt className={styles.label}>사업자등록번호</dt>
              <dd className={styles.value}>{COMPANY.businessNumber}</dd>
            </div>
            <div className={styles.infoItem}>
              <dt className={styles.label}>주소</dt>
              <dd className={styles.value}>{COMPANY.address}</dd>
            </div>
            <div className={styles.infoItem}>
              <dt className={styles.label}>연락처</dt>
              <dd className={styles.value}>
                <a href={`tel:${COMPANY.phone.replace(/-/g, "")}`}>
                  {COMPANY.phone}
                </a>
              </dd>
            </div>
            <div className={styles.infoItem}>
              <dt className={styles.label}>이메일</dt>
              <dd className={styles.value}>
                <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a>
              </dd>
            </div>
          </dl>
        )}

        <div className={styles.copyright}>
          <span className={styles.copyrightText}>
            © {year}{" "}
            {SHOW_BUSINESS_INFO ? COMPANY.name : "Denvia"}. All rights reserved.
          </span>
          <nav className={styles.legalLinks} aria-label="약관 및 정책">
            <Link href="/legal/terms" className={styles.legalLink}>
              이용약관
            </Link>
            <span aria-hidden className={styles.legalDivider}>
              |
            </span>
            <Link href="/legal/privacy" className={styles.legalLink}>
              개인정보처리방침
            </Link>
          </nav>
        </div>
      </div>
    </footer>
  );
}
