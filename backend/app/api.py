"""
/api/* 엔드포인트 — 화면설계서 5장의 7개. 요청·응답 형식은 schemas.py(= frontend/src/types/api.ts)를 따른다.

오류는 FastAPI 기본 형태 { "detail": "..." } 로 돌려준다(api.ts ApiError).
상태 코드는 프론트엔드가 제안한 값: 404 없는 작업, 409 지금 할 수 없는 요청, 422 잘못된 입력.

  업로드·진행 상태·결과 (2-5), 근거 상세·검토 판단·이력 목록·취소/삭제·리포트 (2-6)
"""
import secrets
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from . import config, progress, serializers
from . import schemas as s
from .db import SessionLocal
from .models import Job, Review, utc_now
from .worker import celery_app

router = APIRouter(prefix='/api')

_CHUNK_BYTES = 1024 * 1024  # 업로드를 1MB씩 나눠 저장한다(500MB를 한 번에 메모리에 올리지 않게)


def get_db():
    """요청 하나마다 DB 세션을 열고, 응답을 보낸 뒤 닫는다"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_job_or_404(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, f'작업을 찾을 수 없습니다: {job_id}')
    return job


@router.post('/videos', status_code=201, response_model=s.UploadVideoResponse, summary='영상 업로드 (SCR-01)')
def upload_video(
    file: UploadFile = File(..., description='영상 파일 (MP4·MOV·AVI·WebM, 최대 500MB)'),
    save_history: bool = Form(True, description='이력 저장 여부'),
    memo: str | None = Form(None, description='메모 (이력 검색 대상)'),
    db: Session = Depends(get_db),
):
    filename = Path(file.filename or 'video').name
    extension = Path(filename).suffix.lower()
    if extension not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(422, f'지원하지 않는 형식입니다({extension or "확장자 없음"}). MP4·MOV·AVI·WebM 영상만 올릴 수 있습니다.')

    job_id = f'job-{secrets.token_hex(6)}'
    stored = config.UPLOAD_DIR / f'{job_id}{extension}'
    size = _save_upload(file, stored)

    job = Job(
        id=job_id,
        filename=filename,
        stored_path=str(stored),
        size_bytes=size,
        memo=(memo or '').strip() or None,
        save_history=save_history,
    )
    db.add(job)
    db.commit()

    # 진행 화면이 바로 '대기'를 볼 수 있게 Redis에 먼저 적고, 워커에게 작업을 넘긴다.
    # send_task는 작업 이름으로 보낸다(API 서버가 분석 코드를 불러올 필요가 없다)
    progress.init(job_id)
    task = celery_app.send_task('analyze_video', args=[job_id])
    job.celery_task_id = task.id
    db.commit()
    return s.UploadVideoResponse(job_id=job_id)


def _save_upload(file: UploadFile, target: Path) -> int:
    """업로드를 조금씩 받아 저장하고 크기를 돌려준다. 500MB를 넘거나 비어 있으면 지우고 422"""
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    size = 0
    with target.open('wb') as out:
        while chunk := file.file.read(_CHUNK_BYTES):
            size += len(chunk)
            if size > config.MAX_UPLOAD_BYTES:
                out.close()
                target.unlink(missing_ok=True)
                raise HTTPException(422, '파일이 최대 500MB를 넘습니다.')
            out.write(chunk)
    if size == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(422, '빈 파일입니다.')
    return size


@router.get('/jobs/{job_id}/status', response_model=s.JobStatusResponse, summary='분석 진행 상태 (SCR-02, 2초 폴링)')
def job_status(job_id: str, db: Session = Depends(get_db)):
    return serializers.job_status(get_job_or_404(db, job_id))


@router.get('/jobs/{job_id}/result', response_model=s.JobResultResponse, summary='분석 결과 (SCR-03·06·07)')
def job_result(job_id: str, db: Session = Depends(get_db)):
    result = serializers.job_result(get_job_or_404(db, job_id))
    if result is None:
        raise HTTPException(409, '아직 분석이 끝나지 않았거나 취소된 작업입니다')
    return result


@router.get('/jobs/{job_id}/evidence', response_model=s.EvidenceResponse, summary='판정 근거 상세 (SCR-04)')
def job_evidence(
    job_id: str,
    roi: s.RoiSelector = Query('all', description='얼굴 부위: all | forehead | left_cheek | right_cheek'),
    db: Session = Depends(get_db),
):
    job = get_job_or_404(db, job_id)
    row = next((e for e in job.evidence if e.roi == roi), None)
    if row is None:
        raise HTTPException(409, '근거 데이터가 없는 작업입니다(분석 불가·진행 중·취소)')
    return row.data


@router.post('/jobs/{job_id}/review', response_model=s.Review, summary='검토자 최종 판단 기록 (SCR-07)')
def save_review(job_id: str, body: s.ReviewRequest, db: Session = Depends(get_db)):
    job = get_job_or_404(db, job_id)
    if job.state != 'hold':
        raise HTTPException(409, '판단 보류 건에만 검토 판단을 기록할 수 있습니다')
    # 작업당 하나. 이미 있으면 덮어쓴다([수정])
    if job.review is None:
        job.review = Review(decision=body.decision, reason=body.reason)
    else:
        job.review.decision, job.review.reason, job.review.reviewed_at = body.decision, body.reason, utc_now()
    db.commit()
    return s.Review(decision=job.review.decision, reason=job.review.reason, reviewed_at=serializers.iso(job.review.reviewed_at))


@router.get('/jobs', response_model=s.JobListResponse, summary='분석 이력 목록 (SCR-05)')
def list_jobs(
    q: str | None = Query(None, description='파일명·작업 ID·메모 통합 검색'),
    verdict: s.VerdictKind | None = Query(None, description='판정 필터'),
    date_from: date | None = Query(None, alias='from', description='기간 시작 YYYY-MM-DD (UTC, 포함)'),
    date_to: date | None = Query(None, alias='to', description='기간 끝 YYYY-MM-DD (UTC, 포함)'),
    sqi_min: float | None = Query(None, ge=0, le=1, description='SQI 하한'),
    review: s.ReviewState | None = Query(None, description='보류 건 검토 상태: pending(검토 대기) | needs_more_review(추가 검토 필요) | reviewed(검토 완료)'),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    # 1) DB에서 거르기: 이력 저장한 작업만, 검색어, 기간
    query = db.query(Job).filter(Job.save_history.is_(True))
    if q and q.strip():
        like = f'%{q.strip()}%'
        query = query.filter(or_(Job.filename.ilike(like), Job.id.ilike(like), Job.memo.ilike(like)))
    if date_from:
        query = query.filter(func.date(Job.created_at) >= date_from.isoformat())
    if date_to:
        query = query.filter(func.date(Job.created_at) <= date_to.isoformat())
    jobs = query.options(selectinload(Job.result), selectinload(Job.review)).order_by(Job.created_at.desc()).all()

    # 2) 파이썬에서 거르기: SQI 하한, 검토 상태 (판정 결과를 봐야 알 수 있는 조건)
    if sqi_min is not None:
        jobs = [j for j in jobs if j.result and j.state in ('done', 'hold') and j.result.sqi >= sqi_min]
    if review and review != 'none':
        jobs = [j for j in jobs if serializers.review_state(j) == review]

    # 3) 판정 칩 건수는 판정 필터를 걸기 전에 센다 (칩을 눌러도 다른 칩의 숫자가 사라지지 않게)
    counts = {kind: 0 for kind in ('real', 'fake', 'hold', 'failed', 'running', 'canceled')}
    for job in jobs:
        counts[serializers.verdict_kind(job)] += 1
    if verdict:
        jobs = [j for j in jobs if serializers.verdict_kind(j) == verdict]

    start = (page - 1) * page_size
    return s.JobListResponse(
        items=[serializers.job_list_item(j) for j in jobs[start : start + page_size]],
        total=len(jobs),
        page=page,
        page_size=page_size,
        counts=counts,
    )


@router.delete('/jobs/{job_id}', response_model=s.DeleteJobResponse, summary='분석 취소(진행 중) 또는 삭제(끝난 작업)')
def cancel_or_delete_job(job_id: str, db: Session = Depends(get_db)):
    job = get_job_or_404(db, job_id)
    if job.state in ('queued', 'running'):
        _cancel(job)
        db.commit()
        return s.DeleteJobResponse(job_id=job_id, action='canceled')
    _delete(db, job)
    db.commit()
    return s.DeleteJobResponse(job_id=job_id, action='deleted')


@router.delete('/jobs', response_model=s.DeleteJobsResponse, summary='선택한 작업 일괄 삭제 (SCR-05, UC-07)')
def delete_jobs(body: s.DeleteJobsRequest, db: Session = Depends(get_db)):
    deleted = []
    for job_id in body.job_ids:
        job = db.get(Job, job_id)
        if job is None:
            continue
        active = job.state in ('queued', 'running')
        if active:
            # 진행 중이면 먼저 취소 표시를 남긴다. 워커가 다음 기록 때 알아채고, 지워진 작업에 결과를 쓰지 않고 멈춘다
            _cancel(job)
        _delete(db, job, keep_progress=active)
        deleted.append(job_id)
    db.commit()
    return s.DeleteJobsResponse(deleted=deleted)


def _cancel(job: Job) -> None:
    """진행 중인 작업 취소: DB와 Redis에 '취소' 표시. 아직 시작 전이면 Celery에 실행 취소를 보낸다"""
    job.state = 'canceled'
    progress.mark_canceled(job.id)
    if job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id)


def _delete(db: Session, job: Job, keep_progress: bool = False) -> None:
    """작업 삭제: 업로드 영상, DB 행(결과·근거·검토는 함께 지워짐), Redis 기록.
    keep_progress: 방금 취소한 진행 중 작업이면 Redis의 '취소' 표시를 남겨 둔다(워커가 보고 멈추도록, 하루 뒤 자동 삭제)"""
    Path(job.stored_path).unlink(missing_ok=True)
    if not keep_progress:
        progress.delete(job.id)
    db.delete(job)


# 리포트 PDF는 아직 자리만 있다. PDF 생성 라이브러리는 나중에 정한다(상세제안서 스택에 없음).
# 프론트엔드 목과 같은 내용 없는 1쪽 PDF를 돌려준다.
_PLACEHOLDER_PDF = '\n'.join([
    '%PDF-1.4',
    '1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj',
    '2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj',
    '3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj',
    'trailer<</Root 1 0 R>>',
    '%%EOF',
]).encode()


@router.get('/jobs/{job_id}/report', summary='결과 리포트 PDF (UC-05) — 지금은 빈 PDF',
            response_class=Response, responses={200: {'content': {'application/pdf': {}}}})
def job_report(job_id: str, db: Session = Depends(get_db)):
    get_job_or_404(db, job_id)
    return Response(
        content=_PLACEHOLDER_PDF,
        media_type='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="report_{job_id}.pdf"'},
    )
