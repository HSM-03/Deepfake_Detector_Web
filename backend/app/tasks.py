"""
분석 작업 — 워커가 실행한다. 업로드 하나를 5단계로 처리하고 결과를 DB에 저장한다.

  1. 업로드·검증: 영상 정보를 실제로 읽는다. 열 수 없으면 '파일 손상', 10초 미만이면 '길이 부족'으로 분석 불가
  2. 전처리·ROI 추적  ┐
  3. 메인 모델 판별   ├ 더미 모드: 정해 둔 시간만큼 진행률을 올리고 dummy.py의 예시 값을 쓴다
  4. rPPG 신호 분석   │ (실제 분석은 3단계(메인 모델)·4단계(rPPG)에서 붙인다)
  5. 융합 판정        ┘ 판정 규칙은 더미 값에도 실제 규칙(fusion.py)을 적용한다

단계 사이마다 취소됐는지 확인한다(progress.Tracker가 JobCanceled를 낸다).
"""
import time
import traceback
from pathlib import Path

from analysis import dummy, fusion
from analysis import settings as analysis_settings
from analysis.video_meta import read_video_meta

from . import progress
from .db import SessionLocal
from .models import Evidence, Failure, Job, Result, utc_now
from .progress import STAGE_INDEX, JobCanceled, Tracker
from .worker import celery_app

ROI_SELECTORS = ('all', 'forehead', 'left_cheek', 'right_cheek')


class AnalysisStopped(Exception):
    """분석 불가: failure에 api.ts FailureInfo 형식의 사유를 담는다"""

    def __init__(self, failure: dict):
        super().__init__(failure['title'])
        self.failure = failure


@celery_app.task(name='analyze_video')
def analyze_video(job_id: str) -> str:
    """작업 하나를 끝까지 처리하고 최종 상태('done' | 'hold' | 'failed' | 'canceled')를 돌려준다"""
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:  # 처리하기 전에 삭제됨
            return 'deleted'
        if job.state == 'canceled':
            return 'canceled'

        tracker = None
        try:
            tracker = Tracker(job_id)
            job.state = 'running'
            db.commit()
            state = _run(db, job, tracker)
            _save_final(db, job_id, state, tracker.finish(state))
            return state

        except JobCanceled:  # 사용자가 취소함 — 하던 일을 버리고 기록만 마무리한다
            db.rollback()
            _save_final(db, job_id, 'canceled', progress.mark_canceled(job_id))
            return 'canceled'

        except Exception as error:
            if tracker is None:  # Redis에 접속조차 못 한 경우: 기록할 곳이 없으니 워커 로그로 남긴다
                raise
            db.rollback()
            job = _fresh_job(db, job_id)
            if job is None:  # 분석 중에 사용자가 작업을 삭제함 — 결과를 남길 곳이 없으니 조용히 멈춘다
                return 'deleted'
            if isinstance(error, AnalysisStopped):  # 분석 불가 조건
                failure = error.failure
            else:  # 예상하지 못한 오류도 '분석 불가'로 남겨 진행 화면이 멈추지 않게 한다
                traceback.print_exc()
                stage = progress.current_stage(tracker.data['stages']) or 'upload'
                failure = _unknown_failure(stage, '분석 중 예상하지 못한 오류가 발생했습니다')
            tracker.data['stages'][STAGE_INDEX[failure['stopped_stage']] - 1]['state'] = 'failed'
            tracker.data['logs'].append({'at': progress.iso_now(), 'stage': failure['stopped_stage'], 'message': failure['title']})
            job.failure = Failure(**failure)
            _save_final(db, job_id, 'failed', tracker.finish('failed'))
            return 'failed'


def _fresh_job(db, job_id: str) -> Job | None:
    """
    DB에서 작업을 새로 읽는다. 분석하는 동안 API가 작업을 지웠을 수 있는데, 세션에 남아 있는 예전 복사본(db.get)을 쓰면
    없는 행을 고치려다 오류(StaleDataError)가 난다. 그래서 복사본을 버리고 실제 DB를 다시 조회한다.
    """
    db.expire_all()
    return db.query(Job).filter(Job.id == job_id).one_or_none()


def _save_final(db, job_id: str, state: str, record: dict) -> None:
    """최종 상태와 진행 기록(단계·로그)을 DB에 남긴다. Redis 기록은 하루 뒤 지워지지만 DB 기록은 남는다"""
    job = _fresh_job(db, job_id)
    if job is None:  # 그사이 삭제됨
        return
    if job.state != 'canceled':  # 취소는 API가 이미 DB에 표시했다
        job.state = state
    job.completed_at = utc_now()
    job.stages = record['stages']
    job.logs = record['logs']
    db.commit()


def _run(db, job: Job, tracker: Tracker) -> str:
    # ── 1. 업로드·검증 (더미 모드에서도 실제로 한다) ──
    tracker.set('upload', 0)
    meta = read_video_meta(Path(job.stored_path))
    if meta is None:
        raise AnalysisStopped(_corrupted_failure())
    job.width, job.height, job.fps = meta.width, meta.height, meta.fps
    job.duration_sec, job.frame_count, job.codec = meta.duration_sec, meta.frame_count, meta.codec
    db.commit()
    if meta.duration_sec < analysis_settings.MIN_DURATION_SEC:
        raise AnalysisStopped(_too_short_failure(meta.duration_sec))
    tracker.set('upload', 100)
    tracker.log('upload', f'업로드·검증 완료 — {meta.codec.upper()}, {meta.width}×{meta.height}, {meta.fps:g}fps, {meta.duration_sec:.1f}초')

    if not analysis_settings.USE_DUMMY_ANALYSIS:
        # 실제 분석은 3단계(메인 모델)·4단계(rPPG)에서 연결한다
        raise AnalysisStopped(_unknown_failure('preprocess', '실제 분석이 아직 연결되지 않았습니다 (USE_DUMMY_ANALYSIS=false)'))
    return _run_dummy(db, job, tracker)


def _run_dummy(db, job: Job, tracker: Tracker) -> str:
    p = dummy.DUMMY_PREFIX
    seconds = analysis_settings.DUMMY_STAGE_SECONDS
    scenario_key = dummy.scenario_from_filename(job.filename)

    # ── 2. 전처리·ROI 추적 ──
    if scenario_key == 'failed':
        _advance(tracker, ['preprocess'], seconds['preprocess'], stop_at=70)
        raise AnalysisStopped(dict(dummy.FAILED_FACE))
    _advance(tracker, ['preprocess'], seconds['preprocess'])
    tracker.log('preprocess', f'{p}전처리 완료 — {job.frame_count}프레임, 얼굴 검출률 98.6%, ROI 3개 추적')

    # ── 3·4. 메인 모델 ∥ rPPG (병렬 단계라 두 진행률을 함께 올린다) ──
    s = dummy.SCENARIOS[scenario_key]
    _advance(tracker, ['model', 'rppg'], max(seconds['model'], seconds['rppg']),
             ratios={'model': seconds['rppg'] / seconds['model'], 'rppg': 1.0})
    tracker.log('model', f'{p}메인 모델 판별 완료 — P_model = {s.p_model:.2f}')
    tracker.log('rppg', f'{p}rPPG 분석 완료 — P_rppg = {s.p_rppg:.2f}')

    # ── 5. 융합 판정 ──
    _advance(tracker, ['fusion'], seconds['fusion'])
    outcome = fusion.fuse(s.p_model, s.p_rppg, s.sqi)
    tracker.log('fusion', f'{p}융합 판정 완료 — SQI = {s.sqi:.2f}, w = {outcome.w:.2f}')

    job.result = Result(
        verdict=outcome.verdict,
        score=outcome.score,
        p_model=s.p_model,
        p_model_std=s.p_model_std,
        p_rppg=s.p_rppg,
        w=outcome.w,
        axis_gap=outcome.axis_gap,
        rppg_low_contribution=outcome.rppg_low_contribution,
        sqi=s.sqi,
        sqi_grade=outcome.sqi_grade,
        sqi_components=s.sqi_components,
        roi_bpm=s.roi_bpm,
        thresholds=fusion.thresholds(),
        interpretation=p + s.interpretation,
    )
    axis_text = _axis_text(s.p_model, s.p_rppg, s.sqi, outcome)
    for roi in ROI_SELECTORS:
        data = dummy.build_evidence(job.id, s, roi, job.fps or 30, job.duration_sec or 20,
                                    outcome.w, axis_text, outcome.rppg_low_contribution)
        job.evidence.append(Evidence(roi=roi, data=data))
    db.commit()
    return 'hold' if outcome.verdict == 'hold' else 'done'


def _advance(tracker: Tracker, keys: list[str], seconds: float, stop_at: int = 100, ratios: dict | None = None) -> None:
    """더미 진행: seconds초 동안 진행률을 stop_at까지 고르게 올린다. 0.5초마다 Redis에 쓴다(쓸 때 취소 여부 확인)"""
    ratios = ratios or {}
    for key in keys:  # 시작하자마자 '진행 중'으로 표시한다(그래야 단계 사이에 진행 중인 단계가 비지 않는다)
        tracker.set(key, 0)
    steps = max(1, int(seconds / 0.5))
    for i in range(1, steps + 1):
        time.sleep(seconds / steps)
        for key in keys:
            tracker.set(key, min(stop_at, round(100 * i / steps * ratios.get(key, 1.0))))
    for key in keys:
        if stop_at >= 100:
            tracker.set(key, 100)


def _axis_text(p_model: float, p_rppg: float, sqi: float, outcome: fusion.FusionOutcome) -> str:
    """두 축 대조 요약 문장 (판정 근거 상세의 특징 벡터 탭)"""
    t = fusion.thresholds()
    if outcome.rppg_low_contribution:
        return (f'SQI({sqi:.2f})가 하한({t["sqi_min"]:.2f}) 미만이라 rPPG 축 기여도가 0에 근접합니다(w = {outcome.w:.2f}). '
                '본 판정은 사실상 메인 모델 단독 결과입니다.')
    if outcome.verdict == 'hold':
        return (f'메인 모델은 {_side(p_model)} 쪽({p_model:.2f}), rPPG 축은 {_side(p_rppg)} 쪽({p_rppg:.2f})으로 평가했습니다. '
                f'축 간 차이 {outcome.axis_gap:.2f}로 상충 임계({t["conflict_gap"]:.2f}) 이상이며 '
                f'SQI({sqi:.2f})는 하한({t["sqi_min"]:.2f})을 넘습니다.')
    level = '높게' if outcome.verdict == 'fake' else '낮게'
    return f'두 축 모두 조작 가능성을 {level} 평가했습니다. 축 간 차이 {outcome.axis_gap:.2f}로 상충 임계({t["conflict_gap"]:.2f}) 미만입니다.'


def _side(p: float) -> str:
    return '가짜' if p >= 0.5 else '진짜'


# ── 분석 불가 사유 (api.ts FailureInfo) ──

def _corrupted_failure() -> dict:
    return {
        'code': 'FILE_CORRUPTED',
        'title': '영상 파일을 열 수 없습니다',
        'stopped_stage': 'upload',
        'stopped_stage_index': STAGE_INDEX['upload'],
        'checks': [{'label': '영상 디코딩', 'measured': '실패', 'criterion': '프레임을 읽을 수 있어야 함', 'passed': False}],
        'suggestions': ['파일이 손상되지 않았는지 확인해 주세요.', 'MP4(H.264)로 다시 저장한 뒤 업로드해 보세요.'],
    }


def _too_short_failure(duration: float) -> dict:
    minimum = analysis_settings.MIN_DURATION_SEC
    return {
        'code': 'VIDEO_TOO_SHORT',
        'title': f'영상 길이가 {minimum:g}초보다 짧습니다',
        'stopped_stage': 'upload',
        'stopped_stage_index': STAGE_INDEX['upload'],
        'checks': [{'label': '영상 길이', 'measured': f'{duration:.1f}초', 'criterion': f'{minimum:g}초 이상', 'passed': False}],
        'suggestions': [f'정면 얼굴이 {minimum:g}초 이상 연속으로 나오는 영상을 사용해 주세요.'],
    }


def _unknown_failure(stage: str, title: str) -> dict:
    return {
        'code': 'UNKNOWN',
        'title': title,
        'stopped_stage': stage,
        'stopped_stage_index': STAGE_INDEX[stage],
        'checks': [],
        'suggestions': ['잠시 후 다시 시도해 주세요. 같은 문제가 계속되면 서버 로그를 확인해 주세요.'],
    }
