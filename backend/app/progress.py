"""
진행률 기록 — 워커가 단계마다 Redis에 쓰고, API가 2초마다 읽는다(진행 상태 화면 SCR-02).

키 하나(job:{id}:progress)에 JSON으로 통째로 저장한다. 작업이 끝나면 같은 내용을 DB(jobs.stages, jobs.logs)에도 남기므로,
Redis가 비워져도 끝난 작업의 기록은 남는다. 진행 중 기록은 하루 뒤 Redis에서 자동으로 지워진다.
"""
import json
import logging
import time
from datetime import datetime, timezone

import redis

from . import config

# 워커 로그(docker compose up 화면, docker compose logs worker)에 단계 시작·완료·최종 상태를 한 줄씩 남긴다.
# 중간 진행률(10%, 20% …)까지 찍으면 로그가 너무 많아지므로 찍지 않는다
_log = logging.getLogger('deepfake.progress')

# 분석 5단계: (키, 화면 이름, 진행 중 안내 문구, 전체 진행률에서의 비중) — 프론트엔드 lib/stages.ts와 같은 이름
STAGES = [
    ('upload', '업로드·검증', '파일을 열어 영상 정보를 확인하고 있습니다', 10),
    ('preprocess', '전처리·ROI 추적', '프레임을 추출하고 얼굴 ROI를 추적하고 있습니다', 25),
    ('model', '메인 모델 판별', '메인 모델과 rPPG 분석을 병렬로 수행하고 있습니다', 25),
    ('rppg', 'rPPG 신호 분석', 'rPPG 신호를 분석하고 있습니다', 25),
    ('fusion', '융합 판정', 'SQI를 산출하고 두 축을 융합하고 있습니다', 15),
]
STAGE_LABEL = {key: label for key, label, _, _ in STAGES}
STAGE_INDEX = {key: i + 1 for i, (key, *_) in enumerate(STAGES)}

FINAL_MESSAGE = {
    'done': '분석이 완료되었습니다',
    'hold': '분석이 완료되었습니다',
    'failed': '분석을 계속할 수 없어 중단했습니다',
    'canceled': '분석이 취소되었습니다',
}

_TTL_SECONDS = 24 * 3600
_client = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _key(job_id: str) -> str:
    return f'job:{job_id}:progress'


def empty_stages() -> list[dict]:
    return [{'key': key, 'label': label, 'state': 'waiting', 'progress': 0} for key, label, _, _ in STAGES]


def read(job_id: str) -> dict | None:
    raw = _client.get(_key(job_id))
    return json.loads(raw) if raw else None


def _write(job_id: str, data: dict) -> None:
    _client.set(_key(job_id), json.dumps(data, ensure_ascii=False), ex=_TTL_SECONDS)


def init(job_id: str) -> None:
    """업로드 직후: 모든 단계 '대기'"""
    _write(job_id, {'state': 'queued', 'message': '분석 대기 중입니다', 'stages': empty_stages(), 'logs': [], 'started_at': None})


def delete(job_id: str) -> None:
    _client.delete(_key(job_id))


def overall_progress(stages: list[dict]) -> int:
    """단계별 진행률을 비중대로 합친 전체 진행률 0~100"""
    weight = {key: w for key, _, _, w in STAGES}
    return round(sum(weight[s['key']] * s['progress'] / 100 for s in stages))


def current_stage(stages: list[dict]) -> str | None:
    """지금 진행 중인 단계. 병렬 구간(메인 모델 ∥ rPPG)에서는 먼저 나오는 것 하나"""
    return next((s['key'] for s in stages if s['state'] == 'running'), None)


class JobCanceled(Exception):
    """사용자가 분석을 취소했다. 워커는 이 예외를 받으면 하던 일을 멈춘다"""


class Tracker:
    """
    워커가 쓰는 진행률 기록기. 바꿀 때마다 Redis에 바로 쓴다.
    쓰기 전에 API가 '취소'로 바꿔 놨는지 확인해서, 취소된 기록을 '진행 중'으로 덮어쓰지 않고 JobCanceled를 낸다.
    """

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.data = read(job_id) or {'stages': empty_stages(), 'logs': [], 'message': '', 'started_at': None}
        if self.data.get('state') == 'canceled':  # 워커가 작업을 받기 전에 이미 취소됨
            raise JobCanceled(job_id)
        self.data['state'] = 'running'
        self.data['started_at'] = self.data.get('started_at') or time.time()
        self._save()

    def _stage(self, key: str) -> dict:
        return next(s for s in self.data['stages'] if s['key'] == key)

    def check_canceled(self) -> None:
        latest = read(self.job_id)
        if latest and latest.get('state') == 'canceled':
            raise JobCanceled(self.job_id)

    def _save(self) -> None:
        self.check_canceled()
        running = current_stage(self.data['stages'])
        if self.data['state'] == 'running' and running:
            self.data['message'] = next(m for k, _, m, _ in STAGES if k == running)
        _write(self.job_id, self.data)

    def set(self, key: str, progress: int) -> None:
        """단계 진행률 갱신 (0이면 시작, 100이면 완료)"""
        stage = self._stage(key)
        before = stage['state']
        stage['progress'] = max(0, min(100, int(progress)))
        stage['state'] = 'done' if stage['progress'] >= 100 else 'running'
        self._save()
        if before == 'waiting' and stage['state'] != 'waiting':
            _log.info('[%s] ▶ %s 시작', self.job_id, STAGE_LABEL[key])
        if before != 'done' and stage['state'] == 'done':
            _log.info('[%s] ✓ %s 완료', self.job_id, STAGE_LABEL[key])

    def log(self, key: str, message: str) -> None:
        self.data['logs'].append({'at': iso_now(), 'stage': key, 'message': message})
        self._save()
        _log.info('[%s]     %s', self.job_id, message)

    def finish(self, state: str) -> dict:
        """끝: 'done' | 'hold' | 'failed' | 'canceled'. 진행 중이던 단계는 실패·취소로 표시하고, 저장한 내용을 돌려준다"""
        for stage in self.data['stages']:
            if stage['state'] == 'running':
                stage['state'] = 'canceled' if state == 'canceled' else 'failed'
        self.data['state'] = state
        self.data['message'] = FINAL_MESSAGE[state]
        _write(self.job_id, self.data)
        reason = f' — {self.data["logs"][-1]["message"]}' if state == 'failed' and self.data['logs'] else ''
        _log.info('[%s] ■ 최종 상태: %s%s', self.job_id, state, reason)
        return self.data


def mark_canceled(job_id: str) -> dict:
    """
    취소 표시: 진행 중이던 단계를 '취소됨'으로 바꾸고 저장한 내용을 돌려준다.
    API의 취소 요청이 부르고(워커는 다음 기록 때 알아채고 멈춘다), 워커도 멈추면서 한 번 더 부른다.
    """
    data = read(job_id) or {'stages': empty_stages(), 'logs': [], 'started_at': None}
    for stage in data['stages']:
        if stage['state'] == 'running':
            stage['state'] = 'canceled'
    data['state'] = 'canceled'
    data['message'] = FINAL_MESSAGE['canceled']
    _write(job_id, data)
    _log.info('[%s] ■ 취소됨', job_id)
    return data
