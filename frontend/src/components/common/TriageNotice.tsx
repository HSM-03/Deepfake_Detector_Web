/** 결과 화면 하단에 고정하는 '1차 선별(triage) 도구' 고지 문구 */
export function TriageNotice() {
  return (
    <p className="triage-notice" role="note">
      <span aria-hidden="true">ⓘ</span>
      <span>
        이 시스템은 1차 선별(triage) 도구입니다. 판정 결과는 최종 진위 확정이 아니며, 중요한 판단에는 추가 검증이
        필요합니다.
      </span>
    </p>
  );
}
