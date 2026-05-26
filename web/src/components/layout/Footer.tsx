import Image from "next/image";
import Link from "next/link";
import styles from "./Footer.module.css";

const COMPANY = {
  name: "더플랜",
  representative: "이규성",
  businessNumber: "399-71-00496",
  address: "경기도 가평군 가평읍 향교로27번길 4-32, 201호(한성연립)",
  email: "dlrbtjd357@naver.com",
  phone: "010-2323-2753",
};

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

        <div className={styles.copyright}>
          <span className={styles.copyrightText}>
            © {year} {COMPANY.name}. All rights reserved.
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
