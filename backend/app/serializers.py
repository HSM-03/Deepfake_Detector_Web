"""DB·Redis에 있는 값을 API 응답 형식(schemas.py = api.ts)으로 바꾼다"""
import time
from datetime import datetime, timezone

from . import progress
from . import schemas as s
from .models import Job


def iso(value: datetime | None) -> str:
    """UTC ISO 8601 문자열. SQLite는 시간대 정보를 버리므로 시간대가 없으면 UTC로 본다"""
    if value is None:
        return ''
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def job_status(job: Job) -> s.JobStatusResponse:
    """진행 중이면 Redis의 실시간 기록, 없으면(끝난 지 오래된 작업) DB의 최종 기록으로 만든다"""
    live = progress.read(job.id)
    if live:
        stages, logs, message = live['stages'], live['logs'], live.get('message', '')
        state = 'canceled' if job.state == 'canceled' else live.get('state', job.state)
    else:
        stages = job.stages or progress.empty_stages()
        logs = job.logs or []
        state = job.state
        message = progress.FINAL_MESSAGE.get(state, '분석 대기 중입니다')

    overall = 100 if state in ('done', 'hold') else progress.overall_progress(stages)
    eta = None
    if state == 'running' and live and live.get('started_at') and overall > 0:
        elapsed = time.time() - live['started_at']
        eta = max(0, round(elapsed * (100 - overall) / overall))

    return s.JobStatusResponse(
        job_id=job.id,
        filename=job.filename,
        created_at=iso(job.created_at),
        state=state,
        progress=overall,
        current_stage=progress.current_stage(stages) if state == 'running' else None,
        message=message,
        stages=stages,
        logs=logs,
        eta_seconds=eta,
        result_type=state if state in ('done', 'failed', 'hold') else None,
    )


def verdict_kind(job: Job) -> str:
    """이력 판정 칩 종류 (api.ts VerdictKind): 판정이 있으면 그것, 아니면 상태로 (□진짜 ■가짜 ◆보류 ×불가 ◐진행 –취소)"""
    if job.state in ('done', 'hold') and job.result:
        return job.result.verdict
    if job.state == 'failed':
        return 'failed'
    if job.state == 'canceled':
        return 'canceled'
    return 'running'


def review_state(job: Job) -> str:
    """보류 건의 검토 상태: 기록 없음 → 검토 대기(pending), '추가 검토 필요'로 기록 → needs_more_review,
    진짜·가짜로 결론 → 검토 완료(reviewed). 보류가 아니면 none (프론트엔드 lib/verdict.ts reviewStateOf와 같은 규칙)"""
    if job.state != 'hold':
        return 'none'
    if job.review is None:
        return 'pending'
    return 'needs_more_review' if job.review.decision == 'needs_more_review' else 'reviewed'


def list_progress(job: Job) -> int:
    """이력 행의 진행률. 진행 중이면 Redis의 실시간 값, 끝났으면 저장된 단계 기록으로"""
    if job.state in ('done', 'hold'):
        return 100
    if job.state in ('queued', 'running'):
        live = progress.read(job.id)
        return progress.overall_progress(live['stages']) if live else 0
    return progress.overall_progress(job.stages) if job.stages else 0


def job_list_item(job: Job) -> s.JobListItem:
    r = job.result if job.state in ('done', 'hold') else None
    return s.JobListItem(
        job_id=job.id,
        filename=job.filename,
        created_at=iso(job.created_at),
        state=job.state,
        verdict=r.verdict if r else None,
        score=r.score if r else None,
        p_model=r.p_model if r else None,
        p_rppg=r.p_rppg if r else None,
        sqi=r.sqi if r else None,
        review_state=review_state(job),
        memo=job.memo,
        progress=list_progress(job),
    )


def video_meta(job: Job) -> s.VideoMeta:
    return s.VideoMeta(
        filename=job.filename,
        size_bytes=job.size_bytes,
        width=job.width or 0,
        height=job.height or 0,
        fps=job.fps or 0.0,
        duration_sec=job.duration_sec or 0.0,
        frame_count=job.frame_count or 0,
        codec=job.codec or '',
    )


def job_result(job: Job) -> s.DoneResult | s.HoldResult | s.FailedResult | None:
    """끝난 작업의 결과. 아직 진행 중이거나 취소된 작업이면 None"""
    base = dict(
        job_id=job.id,
        created_at=iso(job.created_at),
        completed_at=iso(job.completed_at),
        video=video_meta(job),
        memo=job.memo,
    )
    if job.state == 'failed' and job.failure:
        f = job.failure
        return s.FailedResult(
            **base,
            result_type='failed',
            failure=s.FailureInfo(
                code=f.code, title=f.title, stopped_stage=f.stopped_stage,
                stopped_stage_index=f.stopped_stage_index, checks=f.checks, suggestions=f.suggestions,
            ),
        )
    if job.state not in ('done', 'hold') or job.result is None:
        return None

    r = job.result
    scored = dict(
        p_model=r.p_model,
        p_model_std=r.p_model_std,
        p_rppg=r.p_rppg,
        p_rppg_provisional=bool(r.p_rppg_provisional),
        w=r.w,
        sqi=s.SqiInfo(value=r.sqi, grade=r.sqi_grade, components=r.sqi_components),
        roi_bpm=r.roi_bpm,
        thresholds=r.thresholds,
        interpretation=r.interpretation,
    )
    if job.state == 'hold':
        review = None
        if job.review:
            review = s.Review(decision=job.review.decision, reason=job.review.reason, reviewed_at=iso(job.review.reviewed_at))
        return s.HoldResult(**base, **scored, result_type='hold', verdict='hold', score=None, axis_gap=r.axis_gap, review=review)
    return s.DoneResult(
        **base, **scored, result_type='done', verdict=r.verdict, score=r.score, rppg_low_contribution=r.rppg_low_contribution,
    )
