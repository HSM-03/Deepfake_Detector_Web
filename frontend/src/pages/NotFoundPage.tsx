import { Link } from 'react-router-dom';
import { paths } from '@/lib/paths';

export function NotFoundPage() {
  return (
    <section className="stack">
      <h1>페이지를 찾을 수 없습니다</h1>
      <p className="muted">주소가 바뀌었거나 삭제된 분석일 수 있습니다.</p>
      <div>
        <Link to={paths.upload()} className="btn btn--primary">
          새 분석
        </Link>
      </div>
    </section>
  );
}
