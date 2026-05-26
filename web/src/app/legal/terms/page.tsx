import Link from "next/link";
import type { Metadata } from "next";
import { Footer } from "@/components/layout/Footer";
import styles from "@/styles/legal.module.css";

export const metadata: Metadata = {
  title: "이용약관 | Denvia",
  description: "Denvia 서비스 이용약관",
};

/**
 * 이용약관 — 회원가입 동의 및 마이페이지에서 참조.
 * 정식 시행 전 법무 검토 필요. 원본 마크다운: docs/legal/terms.md
 */
export default function TermsPage() {
  return (
    <main className={styles.pageMain}>
      <article className={styles.container}>
        <Link href="/" className={styles.backLink}>← 홈으로</Link>

        <h1 className={styles.title}>이용약관</h1>
        <p className={styles.meta}>시행일자: 2026-04-30 (제4조 선택 입력 항목 신설 2026-05-26 시행 예정) · 버전 0.2</p>

        <p className={styles.draftBanner}>
          본 약관은 서비스 정식 출시 전 심사용 초안입니다. 정식 시행 시 사전 공지 후 적용됩니다.
        </p>

        <p className={styles.paragraph}>
          본 약관은 Denvia(이하 &ldquo;회사&rdquo;)가 제공하는 치과 보험청구 및 데스크 행정업무 정보
          안내 AI 보조 서비스 &ldquo;Denvia&rdquo;(이하 &ldquo;서비스&rdquo;)의 이용과 관련하여
          회사와 회원 간의 권리, 의무 및 책임사항을 규정합니다.
        </p>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>제1조 (목적)</h2>
          <p className={styles.paragraph}>
            이 약관은 회원이 회사가 제공하는 서비스를 이용함에 있어 필요한 사항을 정함을 목적으로 합니다.
          </p>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>제2조 (용어의 정의)</h2>
          <ol className={styles.list}>
            <li>
              <span className={styles.emphasis}>&ldquo;서비스&rdquo;</span>란 회사가 제공하는 치과
              보험청구 및 데스크 행정업무 정보에 대한 인공지능 기반 질의응답 보조 도구를 의미합니다.
            </li>
            <li>
              <span className={styles.emphasis}>&ldquo;회원&rdquo;</span>이란 본 약관에 동의하고 회사와 서비스
              이용계약을 체결한 자를 의미합니다.
            </li>
            <li>
              <span className={styles.emphasis}>&ldquo;가입유형&rdquo;</span>이란 치과의사·치과위생사·학생/기타 중
              회원이 선택한 직군 분류를 의미합니다.
            </li>
            <li>
              <span className={styles.emphasis}>&ldquo;AI 답변&rdquo;</span>이란 서비스가 학습된 자료를 바탕으로
              생성한 자동 응답을 의미합니다.
            </li>
          </ol>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>제3조 (약관의 게시 및 변경)</h2>
          <ol className={styles.list}>
            <li>회사는 본 약관의 내용을 회원이 쉽게 알 수 있도록 서비스 초기 화면 및 회원가입 화면에 게시합니다.</li>
            <li>
              회사는 관련 법령을 위배하지 않는 범위에서 본 약관을 변경할 수 있으며, 변경 시에는 적용일자 및 변경
              사유를 명시하여 적용일자 7일 전(회원에게 불리한 변경의 경우 30일 전)부터 서비스 내 공지 또는
              알림톡을 통해 통지합니다.
            </li>
            <li>
              회원은 변경된 약관에 동의하지 않을 경우 회원 탈퇴를 요청할 수 있으며, 변경 약관 시행일 이후에도
              서비스를 계속 이용하는 경우 변경에 동의한 것으로 간주합니다.
            </li>
          </ol>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>제4조 (회원가입 및 자격)</h2>
          <ol className={styles.list}>
            <li>
              회원가입은 이용 신청자가 약관 및 개인정보 처리방침에 동의하고, 회사가 정한 가입 양식에 정보를 기입한
              후 휴대폰 SMS 인증을 완료함으로써 성립합니다.
            </li>
            <li>
              회사는 회원가입 단계에서 <span className={styles.emphasis}>필수 정보</span>(이메일·비밀번호·휴대폰
              번호) 외에 <span className={styles.emphasis}>선택 정보</span>(이름·생년월일·성별·주소)를 수집할 수
              있습니다. 선택 정보는 입력하지 않아도 가입 및 서비스 이용에 제한이 없으며, 회원은 가입 후
              마이페이지에서 언제든지 입력·수정·삭제할 수 있습니다. 선택 정보의 수집·이용에 관한 자세한 사항은{" "}
              <Link href="/legal/privacy">개인정보 처리방침</Link>에 따릅니다.
            </li>
            <li>본 서비스는 만 14세 이상의 자에 한하여 가입할 수 있습니다.</li>
            <li>
              회사는 다음 각 호에 해당하는 신청에 대하여는 가입을 승낙하지 않거나 사후에 이용계약을 해지할 수
              있습니다.
              <ul className={styles.list}>
                <li>타인의 명의·휴대폰을 도용하여 신청한 경우</li>
                <li>허위 정보를 기재하거나 회사가 요구하는 정보를 기재하지 않은 경우</li>
                <li>부정한 용도로 서비스를 이용하고자 하는 경우</li>
              </ul>
            </li>
          </ol>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>제5조 (서비스의 제공)</h2>
          <ol className={styles.list}>
            <li>
              회사는 회원에게 다음과 같은 서비스를 제공합니다.
              <ul className={styles.list}>
                <li>치과 보험청구 및 데스크 행정업무 정보에 대한 AI 질의응답</li>
                <li>가입유형별 맞춤형 정보 제공</li>
                <li>기타 회사가 추가로 개발하거나 제휴를 통해 제공하는 서비스</li>
              </ul>
            </li>
            <li>
              서비스는 연중무휴, 1일 24시간 제공함을 원칙으로 합니다. 다만 시스템 점검·증설·교체 등 운영상 필요에
              의해 일시 중단될 수 있으며, 이 경우 사전 또는 사후에 공지합니다.
            </li>
          </ol>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>제6조 (AI 답변의 성격 및 면책)</h2>
          <ol className={styles.list}>
            <li>
              <span className={styles.emphasis}>
                본 서비스의 AI 답변은 일반적인 정보 제공을 목적으로 하며, 의료 진단·처방·치료 권고에 해당하지
                않습니다.
              </span>{" "}
              실제 보험청구 제출·진료 결정은 자격 있는 치과 전문가의 직접 판단과 책임 하에
              이루어져야 합니다.
            </li>
            <li>
              AI 답변은 학습 자료의 범위 및 모델의 특성상 부정확하거나 최신 정보가 아닐 수 있습니다. 회원은 답변
              내용을 검토 후 활용하여야 하며, 답변에 의존한 결정으로 발생한 손해에 대하여 회사는 고의 또는 중대한
              과실이 없는 한 책임을 지지 않습니다.
            </li>
            <li>회원은 AI 답변을 환자에 대한 진단 또는 치료 행위의 단독 근거로 사용하여서는 아니 됩니다.</li>
          </ol>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>제7조 (회원의 의무)</h2>
          <p className={styles.paragraph}>회원은 다음 행위를 하여서는 안 됩니다.</p>
          <ol className={styles.list}>
            <li>타인의 정보 도용</li>
            <li>회사 또는 제3자의 지적재산권 침해</li>
            <li>서비스의 안정적 운영을 방해할 수 있는 정보 송신·게시</li>
            <li>서비스를 통해 얻은 정보를 회사의 사전 동의 없이 복제·유통하거나 상업적으로 이용하는 행위</li>
            <li>자동화된 수단(크롤러·봇 등)을 통한 비정상적 접근</li>
          </ol>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>제8조 (유료 서비스)</h2>
          <ol className={styles.list}>
            <li>
              회사는 일부 기능을 유료 서비스(이하 &ldquo;Pro&rdquo;)로 제공할 수 있으며, 결제는 ㈜토스페이먼츠를
              통해 처리됩니다.
            </li>
            <li>Pro 월 이용료는 9,900원(부가세 포함)이며, 가격 변경 시 제3조 제2항에 따라 사전 통지합니다.</li>
            <li>
              결제수단은 카드 정기결제(빌링)를 원칙으로 하며, 회원은 마이페이지에서 등록된 결제수단을 언제든지
              변경할 수 있습니다.
            </li>
          </ol>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>제9조 (자동 갱신)</h2>
          <ol className={styles.list}>
            <li>Pro 구독은 매월 동일 일자에 자동 갱신됩니다.</li>
            <li>
              자동 갱신을 원하지 않는 회원은 다음 결제일 전일까지 마이페이지에서 해지 신청을 하여야 합니다.
            </li>
            <li>
              갱신 결제 실패 시 회사는 최대 3회까지 자동 재시도하며, 모든 재시도가 실패할 경우 구독은 해지되고
              알림톡으로 안내됩니다.
            </li>
          </ol>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>제10조 (해지 및 환불)</h2>
          <ol className={styles.list}>
            <li>회원은 언제든지 마이페이지에서 구독 해지를 신청할 수 있습니다.</li>
            <li>
              해지 시점에 따른 환불 정책은 다음과 같습니다.
              <ul className={styles.list}>
                <li>결제일로부터 7일 이내이고 서비스 이용 이력이 없는 경우: 전액 환불</li>
                <li>결제일로부터 7일 이내이고 서비스 이용 이력이 있는 경우: 일할 계산 후 잔여분 환불</li>
                <li>
                  결제일로부터 7일 초과 시: 잔여 기간에 대한 환불 없음. 단, 이미 결제된 기간까지는 서비스 이용 가능
                </li>
              </ul>
            </li>
            <li>회원이 본 약관 제7조를 위반하여 회사가 직권 해지하는 경우 환불하지 아니합니다.</li>
          </ol>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>제11조 (서비스 일시 중단 및 기간 자동 연장)</h2>
          <ol className={styles.list}>
            <li>
              회사는 다음 각 호의 사유로 서비스를 일시 중단할 수 있습니다.
              <ul className={styles.list}>
                <li>시스템 점검·증설·교체</li>
                <li>보안 인시던트 또는 데이터 무결성 위협 감지</li>
                <li>운영비용 초과로 인한 시스템 보호 조치</li>
                <li>천재지변 등 불가항력</li>
              </ul>
            </li>
            <li>
              <span className={styles.emphasis}>
                제1항에 따른 일시 중단으로 Pro 회원의 서비스 이용이 제한된 경우, 회사는 중단 시간(분 단위)만큼 해당
                회원의 구독 만료일을 자동 연장합니다.
              </span>
            </li>
          </ol>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>제12조 (개인정보 보호)</h2>
          <p className={styles.paragraph}>
            회사는 회원의 개인정보를 보호하기 위해 노력하며, 개인정보의 수집·이용·제공 등에 관한 사항은 별도의{" "}
            <Link href="/legal/privacy">개인정보 처리방침</Link>에 따릅니다.
          </p>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>제13조 (회사의 면책)</h2>
          <ol className={styles.list}>
            <li>
              회사는 천재지변, 전쟁, 정전, 통신 두절 등 불가항력으로 인하여 서비스를 제공할 수 없는 경우 책임이
              면제됩니다.
            </li>
            <li>회사는 회원의 귀책사유로 인한 서비스 이용 장애에 대하여 책임을 지지 않습니다.</li>
            <li>
              회사는 회원이 서비스를 이용하여 기대하는 손익이나 서비스를 통하여 얻은 정보로 인한 손해에 대하여 고의
              또는 중과실이 없는 한 책임을 지지 않습니다.
            </li>
          </ol>
        </section>

        <section id="killswitch-extension" className={styles.section}>
          <h2 className={styles.sectionTitle}>제14조 (서비스 비상 정지 시 유료 구독 자동 연장)</h2>
          <ol className={styles.list}>
            <li>
              회사는 결제 시스템 장애·외부 API 장애·이상 트래픽 등 비상 상황에서 서비스를
              일시 정지(이하 &ldquo;비상 정지&rdquo;)할 수 있습니다.
            </li>
            <li>
              비상 정지로 인해 활성 유료 구독자가 서비스를 이용하지 못한 경우, 회사는 정지
              시점부터 해제 시점까지의 기간만큼 해당 회원의 다음 결제일 및 구독 만료일을
              자동으로 연장합니다(분 단위 정확).
            </li>
            <li>연장 결과는 알림톡(또는 SMS 폴백)으로 회원에게 통지됩니다.</li>
            <li>비상 정지 기간 중 신규 결제 재시도는 자동 보류되며, 해제 후 자동 재개됩니다.</li>
          </ol>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>제15조 (분쟁 해결)</h2>
          <ol className={styles.list}>
            <li>본 약관과 관련하여 회사와 회원 간에 발생한 분쟁에 대해서는 대한민국 법을 준거법으로 합니다.</li>
            <li>분쟁이 소송으로 진행될 경우 민사소송법상의 관할법원에 제소합니다.</li>
          </ol>
        </section>

        <p className={styles.footer}>
          부칙 — 본 약관은 2026-04-30 부터 시행합니다. 제4조 제2항(회원가입 단계의 선택 정보 수집) 신설은
          2026-05-26 부터 시행합니다. 회원에게 선택 정보(이름·생년월일·성별·주소)를 가입 단계에서 입력할 수 있는
          옵션을 부여하는 내용으로, 필수 입력은 아니므로 미입력 시에도 가입 및 서비스 이용에 제한이 없습니다.
        </p>
      </article>
      <Footer />
    </main>
  );
}
