"""
분석 작업 — 워커가 실행한다. 업로드 하나를 5단계로 처리하고 결과를 DB에 저장한다.

  1. 업로드·검증: 영상 정보를 실제로 읽는다. 열 수 없으면 '파일 손상', 10초 미만이면 '길이 부족'으로 분석 불가
  2. 전처리·ROI 추적  ┐ 메인 모델: 실제 EfficientNet-B4(analysis/main_model.py). 얼굴 검출률이 기준 미만이면 '얼굴 미검출'
  3. 메인 모델 판별   ┘ USE_DUMMY_MAIN_MODEL을 켜면 모델 없이 더미 값으로 흉내 낸다
  4. rPPG 신호 분석     실제: 얼굴 ROI 추적 → 특징 6개 → SQI → P_rppg 분류기(5단계, analysis/p_rppg.py).
                       USE_DUMMY_P_RPPG를 켜면 예전처럼 P_rppg = P_model(임시 값)
                       USE_DUMMY_RPPG를 켜면 예전 더미 시나리오(파일 이름 키워드)로 동작한다
  5. 융합 판정          판정 규칙은 어느 경우든 실제 규칙(fusion.py)을 적용한다

단계 사이마다 취소됐는지 확인한다(progress.Tracker가 JobCanceled를 낸다).
"""
import logging
import os
import time
import traceback
from pathlib import Path

from analysis import dummy, fusion, interpret, p_rppg as p_rppg_classifier, rppg_evidence, rppg_features, sqi
from analysis import rppg as rppg_signal
from analysis.stream_info import stream_info
from analysis import settings as analysis_settings
from analysis.video_meta import VideoMeta, read_video_meta

from . import progress
from .db import SessionLocal
from .models import Evidence, Failure, Job, Result, utc_now
from .progress import STAGE_INDEX, JobCanceled, Tracker
from .worker import celery_app

ROI_SELECTORS = ('all', 'forehead', 'left_cheek', 'right_cheek')

_log = logging.getLogger('deepfake.tasks')

# 메인 모델은 워커 프로세스마다 처음 작업을 받을 때 한 번만 불러 두고 계속 쓴다.
# API 서버도 이 파일을 불러오므로(작업을 큐에 넣으려고) PyTorch는 여기서 바로 불러오지 않는다
_main_model = None


def _get_main_model():
    global _main_model
    if _main_model is None:
        import torch

        from analysis.main_model import MainModel

        started = time.perf_counter()
        _main_model = MainModel()
        _log.info('메인 모델 불러옴: %.1f초, PyTorch 스레드 %d개 (CPU %d개)',
                  time.perf_counter() - started, torch.get_num_threads(), os.cpu_count() or 0)
    return _main_model


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

        # 같은 작업이 다시 넘어올 수 있다. 워커는 작업을 '끝낸 뒤에' 처리 완료를 알리는데(task_acks_late),
        # 알리기 직전에 워커가 꺼지면 Redis가 같은 작업을 다음 워커에게 다시 준다. 그래서 상태를 보고 안전하게 처리한다.
        if job.state in ('done', 'hold', 'failed'):  # 이미 끝난 작업: 결과를 건드리지 않는다
            _log.info('[%s] 이미 끝난 작업(%s)이 다시 넘어와 건너뜀', job_id, job.state)
            return job.state
        if job.state == 'running':  # 이전 시도가 도중에 끊김: 남은 결과를 지우고 처음부터 다시 한다
            _log.info('[%s] 이전 시도가 중단되어 처음부터 다시 분석함', job_id)
            job.result = None
            job.failure = None
            job.evidence.clear()
            job.state = 'queued'
            db.commit()
            progress.init(job_id)

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

    return _analyze(db, job, tracker)


def _analyze(db, job: Job, tracker: Tracker) -> str:
    """
    2~5단계. 메인 모델과 rPPG는 각각 설정에 따라 더미 값 또는 실제 분석 값을 쓴다.
      - USE_DUMMY_MAIN_MODEL: 켜져 있으면 전처리·메인 모델을 흉내 내고 dummy.dummy_main_model 값을 쓴다
      - USE_DUMMY_RPPG: 켜져 있으면 dummy.dummy_rppg 값을 쓴다(키워드가 없으면 P_rppg = P_model)
    판정은 어느 경우든 실제 규칙(fusion.py)으로 낸다.
    """
    p = dummy.DUMMY_PREFIX
    seconds = analysis_settings.DUMMY_STAGE_SECONDS
    dummy_main = analysis_settings.USE_DUMMY_MAIN_MODEL
    dummy_rppg = analysis_settings.USE_DUMMY_RPPG
    scenario_key = dummy.scenario_from_filename(job.filename)

    # ── 2. 전처리·ROI 추적 / 3. 메인 모델 ──
    if dummy_main:
        main = _dummy_main_model(job, tracker, scenario_key)
    else:
        main = _real_main_model(db, job, tracker)

    # ── 4. rPPG ──
    if dummy_rppg:
        result = _dummy_rppg_stage(job, tracker, main, dummy_main)
    else:
        result = _real_rppg_stage(job, tracker, main)

    # ── 5. 융합 판정 (규칙은 실제) ──
    _advance(tracker, ['fusion'], seconds['fusion'])
    outcome = fusion.fuse(main.p_model, result['p_rppg'], result['sqi'])
    tracker.log('fusion', f'{p if dummy_rppg else ""}융합 판정 완료 — SQI = {result["sqi"]:.2f}, w = {outcome.w:.2f}'
                + (' (rPPG 미반영: 신호 품질 낮음)' if outcome.rppg_low_contribution else ''))

    interpretation = interpret.interpretation(
        outcome, main.p_model, result['p_rppg'], result['sqi'],
        face_count=None if dummy_main else job.face_frames_detected,
        profile=main.profile,
        rppg_is_dummy=dummy_rppg and not dummy_main,
        rppg_mirrors_model=result['mirrors'],
        rppg_measured=result['measured'],
    )
    axis_text = interpret.axis_summary(outcome, main.p_model, result['p_rppg'], result['sqi'],
                                       rppg_mirrors_model=result['mirrors'], rppg_measured=result['measured'])
    job.result = Result(
        verdict=outcome.verdict,
        score=outcome.score,
        p_model=round(main.p_model, 3),
        p_model_std=round(main.p_model_std, 3),
        p_rppg=round(result['p_rppg'], 3),
        w=outcome.w,
        axis_gap=outcome.axis_gap,
        rppg_low_contribution=outcome.rppg_low_contribution,
        p_rppg_provisional=result['provisional'],
        sqi=result['sqi'],
        sqi_grade=outcome.sqi_grade,
        sqi_components=result['sqi_components'],
        roi_bpm=result['roi_bpm'],
        thresholds=fusion.thresholds(),
        interpretation=(p if dummy_main else '') + interpretation,
    )
    axis_summary = {'p_model': round(main.p_model, 3), 'p_rppg': round(result['p_rppg'], 3), 'w': outcome.w,
                    'sqi': result['sqi'], 'text': (p if (dummy_main or dummy_rppg) else '') + axis_text}
    for roi in ROI_SELECTORS:
        job.evidence.append(Evidence(roi=roi, data=result['evidence'](roi, outcome, axis_summary)))
    tracker.check_canceled()  # 마지막 기록 뒤에 취소됐으면 결과를 남기지 않는다(JobCanceled → rollback)
    db.commit()
    return 'hold' if outcome.verdict == 'hold' else 'done'


def _real_rppg_stage(job: Job, tracker: Tracker, main: dummy.MainModelValues) -> dict:
    """
    실제 rPPG: 영상 전체 프레임의 얼굴 ROI 추적 → 특징 6개(rppg_features, FF++ 검증과 같은 함수) → SQI.
    P_rppg는 특징 6개로 분류기(FF++ c0로 학습한 로지스틱 회귀, analysis/p_rppg_model.json)가 낸다.
    USE_DUMMY_P_RPPG를 켜면 예전처럼 P_model 값을 임시로 쓴다(판정은 메인 모델 단독과 같음).
    추적 중에는 진행률을 쓸 때마다 취소를 확인하므로 취소하면 바로 멈춘다.
    """
    path = Path(job.stored_path)
    meta = VideoMeta(width=job.width, height=job.height, fps=job.fps, duration_sec=job.duration_sec,
                     frame_count=job.frame_count, codec=job.codec)
    tracker.set('rppg', 0)
    # 긴 영상은 앞 RPPG_MAX_ANALYSIS_SEC초만 (처리 시간이 길이에 비례). 메인 모델은 영상 전체에서 32프레임 그대로
    max_frames = int(round(analysis_settings.RPPG_MAX_ANALYSIS_SEC * meta.fps)) if meta.fps else None
    truncated = bool(max_frames and meta.frame_count > max_frames)
    analyzed_sec = min(meta.duration_sec or 0.0, analysis_settings.RPPG_MAX_ANALYSIS_SEC)
    traces = rppg_signal.extract_traces(path, meta, on_progress=lambda r: tracker.set('rppg', min(95, int(r * 95))),
                                        max_frames=max_frames)
    features = rppg_features.compute(traces)
    quality = sqi.compute(traces, meta.codec, stream_info(path, meta))
    tracker.set('rppg', 100)
    hr = features.hr_bpm
    # 네 항목이 모두 1이면 깎은 항목이 없다(로그에 첫 항목 이름이 찍히지 않게)
    weakest = interpret.SQI_COMPONENT_LABELS[quality.weakest] if quality.value < 1 else '없음'
    tracker.log('rppg', f'rPPG 분석 완료 — 심박 {"측정 실패" if hr is None else f"{hr:.0f}BPM"}, SQI {quality.value:.2f}'
                        f' (가장 약한 항목: {weakest}), 얼굴 추적 {traces.tracked_rate:.0%}'
                        + (f', 영상 {meta.duration_sec:.0f}초 중 앞 {analyzed_sec:.0f}초 분석' if truncated else ''))
    provisional = analysis_settings.USE_DUMMY_P_RPPG
    p_rppg = main.p_model if provisional else p_rppg_classifier.p_rppg(features.values)
    if not provisional:
        tracker.log('rppg', f'P_rppg 분류기 — {p_rppg:.2f} ({"가짜" if p_rppg >= 0.5 else "진짜"} 쪽)')
    roi_bpm = {k: None if b is None else round(float(b), 1) for k, b in features.roi_bpm.items()}
    profile = main.profile or []

    def evidence(roi: str, outcome: fusion.FusionOutcome, axis_summary: dict) -> dict:
        return rppg_evidence.build(job.id, roi, traces, features, profile, axis_summary, outcome.rppg_low_contribution,
                                   analyzed_sec, truncated, provisional=provisional)

    return {'p_rppg': p_rppg, 'sqi': quality.value, 'sqi_components': quality.components, 'roi_bpm': roi_bpm,
            'mirrors': provisional,
            'measured': {'hr': hr, 'weakest': quality.weakest, 'truncated_sec': analyzed_sec if truncated else None,
                         'provisional': provisional},
            'evidence': evidence, 'provisional': provisional}


def _dummy_rppg_stage(job: Job, tracker: Tracker, main: dummy.MainModelValues, dummy_main: bool) -> dict:
    """USE_DUMMY_RPPG를 켰을 때: 예전 더미 시나리오(키워드가 없으면 P_rppg = P_model). 판단 보류 등 화면 확인용"""
    p = dummy.DUMMY_PREFIX
    seconds = analysis_settings.DUMMY_STAGE_SECONDS
    values = dummy.dummy_rppg(job.filename, main.p_model)
    if dummy_main:  # 메인 모델 ∥ rPPG는 병렬 단계라 두 진행률을 함께 올린다
        _advance(tracker, ['model', 'rppg'], max(seconds['model'], seconds['rppg']),
                 ratios={'model': seconds['rppg'] / seconds['model'], 'rppg': 1.0})
        tracker.log('model', f'{p}메인 모델 판별 완료 — P_model = {main.p_model:.2f}')
    else:
        _advance(tracker, ['rppg'], seconds['rppg_after_main'])
    tracker.log('rppg', f'{p}rPPG 분석 완료 — P_rppg = {values.p_rppg:.2f}')

    def evidence(roi: str, outcome: fusion.FusionOutcome, axis_summary: dict) -> dict:
        data = dummy.build_evidence(job.id, roi, job.fps or 30, job.duration_sec or 20, main, values,
                                    outcome.w, '', outcome.rppg_low_contribution, axis_text_prefix='')
        data['axis_summary'] = axis_summary
        data.update(p_rppg_provisional=False, rppg_analyzed_sec=float(job.duration_sec or 0.0), rppg_truncated=False)
        return data

    return {'p_rppg': values.p_rppg, 'sqi': values.sqi, 'sqi_components': values.sqi_components,
            'roi_bpm': values.roi_bpm, 'mirrors': dummy.rppg_follows_model(job.filename), 'measured': None,
            'evidence': evidence, 'provisional': False}


def _dummy_main_model(job: Job, tracker: Tracker, scenario_key: str) -> dummy.MainModelValues:
    """USE_DUMMY_MAIN_MODEL이 켜져 있을 때: 전처리를 흉내 내고 키워드 시나리오의 P_model을 돌려준다(fail·noface는 얼굴 미검출)"""
    p = dummy.DUMMY_PREFIX
    seconds = analysis_settings.DUMMY_STAGE_SECONDS
    if scenario_key == 'failed':
        _advance(tracker, ['preprocess'], seconds['preprocess'], stop_at=70)
        raise AnalysisStopped(dict(dummy.FAILED_FACE))
    _advance(tracker, ['preprocess'], seconds['preprocess'])
    tracker.log('preprocess', f'{p}전처리 완료 — {job.frame_count}프레임, 얼굴 검출률 98.6%, ROI 3개 추적')
    return dummy.dummy_main_model(job.filename)


def _real_main_model(db, job: Job, tracker: Tracker) -> dummy.MainModelValues:
    """
    실제 메인 모델: 프레임 추출·얼굴 정렬(전처리) → 얼굴 검출률 확인 → EfficientNet-B4(메인 모델 판별).
    파일 이름 키워드(fail 등)는 여기서 쓰지 않는다. 진행률은 main_model이 알려 주는 대로 Redis에 쓰고,
    쓸 때마다 취소 여부를 확인한다(모델 계산 중의 취소는 계산이 끝난 뒤 반영된다).
    """
    model = _get_main_model()
    meta = VideoMeta(width=job.width, height=job.height, fps=job.fps, duration_sec=job.duration_sec,
                     frame_count=job.frame_count, codec=job.codec)

    def preprocess_progress(stage: str, percent: int) -> None:
        # 100%는 얼굴 검출률을 확인한 뒤에 찍는다(기준 미달이면 전처리 단계에서 실패로 끝나야 하므로)
        tracker.set('preprocess', min(percent, 99))

    prepared = model.prepare(job.stored_path, meta=meta, on_progress=preprocess_progress)
    stats = prepared.stats
    job.face_frames_sampled = stats.frames_sampled
    job.face_frames_detected = stats.frames_with_face
    db.commit()

    face_text = f'얼굴 검출률 {stats.frames_with_face}/{stats.frames_sampled}장 ({stats.face_rate:.1%})'
    if stats.face_rate < analysis_settings.MAIN_MODEL_MIN_FACE_RATE:
        raise AnalysisStopped(_face_failure(stats))
    tracker.set('preprocess', 100)
    size = f', 평균 얼굴 {stats.face_box_mean[0]}×{stats.face_box_mean[1]}px' if stats.face_box_mean else ''
    preprocess_sec = prepared.timing_sec['decode'] + prepared.timing_sec['face']
    tracker.log('preprocess', f'전처리 완료 — 프레임 {stats.frames_sampled}장 추출, {face_text}{size}, {preprocess_sec:.1f}초')

    def model_progress(stage: str, percent: int) -> None:
        tracker.set('model', percent)

    import torch

    result = model.score(prepared, on_progress=model_progress)
    tracker.log('model', f'메인 모델 판별 완료 — P_model = {result.p_model:.2f} (표준편차 {result.p_model_std:.2f}),'
                         f' {result.timing_sec["model"]:.1f}초 (PyTorch 스레드 {torch.get_num_threads()}개)')
    return dummy.MainModelValues(
        p_model=result.p_model,
        p_model_std=result.p_model_std,
        profile=[{'t_start': seg.t_start, 't_end': seg.t_end, 'p': seg.p} for seg in result.profile],
    )


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


def _face_failure(stats) -> dict:
    """얼굴 검출률이 MAIN_MODEL_MIN_FACE_RATE 미만 (analysis.main_model.FaceStats의 실제 측정값으로 안내한다)"""
    minimum = analysis_settings.MAIN_MODEL_MIN_FACE_RATE
    # 안내는 측정값에 해당하는 것만 넣는다 (기준값은 settings.py의 예시값, 판정에는 쓰지 않는다)
    suggestions = []
    dark = stats.brightness_mean < analysis_settings.DARK_BRIGHTNESS
    if dark:
        suggestions.append(f'영상이 어둡습니다(평균 밝기 {stats.brightness_mean:.0f}/255). 밝은 곳에서 다시 촬영해 주세요.')
    if stats.frames_no_face >= stats.frames_recheck_failed:  # 얼굴 자체를 못 찾은 프레임이 많음
        suggestions.append('정면 얼굴이 10초 이상 계속 화면에 나오는 구간을 사용해 주세요.')
        if stats.face_box_mean is None and not dark:
            suggestions.append('얼굴을 한 번도 찾지 못했습니다. 얼굴이 화면에서 충분히 크게 보이는지 확인해 주세요.')
        elif stats.face_box_mean and max(stats.face_box_mean) < analysis_settings.FACE_SMALL_PX:
            w, h = stats.face_box_mean
            suggestions.append(f'찾은 얼굴의 평균 크기가 {w}×{h}px로 작습니다. 얼굴이 더 크게 보이도록 잘라낸 뒤 다시 올려 주세요.')
    else:  # 얼굴은 찾았지만 정렬 뒤 다시 검출되지 않은 프레임이 많음
        suggestions.append('얼굴이 옆으로 돌아가 있거나 가려진 장면이 많습니다. 정면 얼굴이 나오는 구간을 사용해 주세요.')
    if not dark:
        suggestions.append('밝고 선명한 영상(720p 이상)을 권장합니다.')
    return {
        'code': 'FACE_NOT_DETECTED',
        'title': '영상에서 얼굴을 충분히 검출하지 못했습니다',
        'stopped_stage': 'preprocess',
        'stopped_stage_index': STAGE_INDEX['preprocess'],
        'checks': [{
            'label': '얼굴 검출 프레임 비율',
            'measured': f'{stats.face_rate:.1%} ({stats.frames_with_face}/{stats.frames_sampled}장)',
            'criterion': f'{minimum:.0%} 이상',
            'passed': False,
        }],
        'suggestions': suggestions,
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
