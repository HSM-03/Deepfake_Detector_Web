import { Link, NavLink } from 'react-router-dom';
import { paths } from '@/lib/paths';

/** 상단 고정 헤더 — [새 분석] [분석 이력] (화면설계서 공통 규격) */
export function AppHeader() {
  return (
    <header className="app-header">
      <div className="app-header__inner">
        <Link to={paths.upload()} className="app-header__brand">
          {/* 방패(진위 판별) 안의 맥파(rPPG) */}
          <span className="app-header__mark" aria-hidden="true">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 3 4.5 6v5.5c0 4.4 3 8 7.5 9.5 4.5-1.5 7.5-5.1 7.5-9.5V6L12 3Z" opacity="0.55" />
              <path d="M7 12.5h2.2l1.5-3 2.3 5.5 1.5-2.5H17" />
            </svg>
          </span>
          <span className="app-header__name">
            <strong>딥페이크 탐지기</strong>
            <small>rPPG 생체신호 교차검증</small>
          </span>
        </Link>
        <nav className="app-header__nav" aria-label="주 메뉴">
          <NavLink to={paths.upload()} end className="app-header__link">
            새 분석
          </NavLink>
          <NavLink to={paths.history()} className="app-header__link">
            분석 이력
          </NavLink>
        </nav>
      </div>
    </header>
  );
}
