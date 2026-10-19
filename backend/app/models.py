"""
DB 테이블 — 계획서 2단계의 5가지: 작업 정보, 판정 결과, 근거 데이터, 분석 불가 사유, 검토자 판단.

API 응답 형식(frontend/src/types/api.ts)과 이름을 맞춰 두었다. 응답으로 바꾸는 일은 API 쪽에서 한다.
파형·스펙트럼처럼 큰 배열은 JSON 칸 하나에 통째로 넣는다(계획서).
시각은 UTC로 저장한다.
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    """작업 정보 — 업로드 1건. 진행 중의 실시간 진행률은 Redis에 있고, 여기에는 최종 상태와 로그가 남는다"""

    __tablename__ = 'jobs'

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # 예: job-3f9a1c2b7d4e
    filename: Mapped[str] = mapped_column(String(255))  # 사용자가 올린 원래 파일명
    stored_path: Mapped[str] = mapped_column(String(512))  # 볼륨 안 저장 위치
    size_bytes: Mapped[int] = mapped_column(Integer)
    memo: Mapped[str | None] = mapped_column(Text, default=None)
    # False면 이력 목록(GET /api/jobs)에서 뺀다. 업로드 직후 결과 화면은 볼 수 있어야 해서 행 자체는 남긴다
    save_history: Mapped[bool] = mapped_column(Boolean, default=True)

    # 'queued' | 'running' | 'done' | 'failed' | 'hold' | 'canceled' (api.ts JobState)
    state: Mapped[str] = mapped_column(String(16), default='queued', index=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(64), default=None)  # 취소할 때 쓴다
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # 영상 정보 (api.ts VideoMeta) — 업로드·검증 단계에서 채운다
    width: Mapped[int | None] = mapped_column(Integer, default=None)
    height: Mapped[int | None] = mapped_column(Integer, default=None)
    fps: Mapped[float | None] = mapped_column(Float, default=None)
    duration_sec: Mapped[float | None] = mapped_column(Float, default=None)
    frame_count: Mapped[int | None] = mapped_column(Integer, default=None)
    codec: Mapped[str | None] = mapped_column(String(16), default=None)

    # 메인 모델 얼굴 검출 통계 — 전처리 단계에서 채운다(완료·판단 보류·분석 불가 모두). 검출률 = 잡힌 수 / 뽑은 수.
    # 3단계에서 추가한 칸이라, 예전 DB에는 init_db가 칸을 붙인다(db.py _ADDED_COLUMNS)
    face_frames_sampled: Mapped[int | None] = mapped_column(Integer, default=None)
    face_frames_detected: Mapped[int | None] = mapped_column(Integer, default=None)

    # 끝난 작업의 단계별 상태와 로그 (api.ts StageStatus[], JobLogEntry[]). 진행 중에는 Redis 값이 우선이다
    stages: Mapped[list | None] = mapped_column(JSON, default=None)
    logs: Mapped[list | None] = mapped_column(JSON, default=None)

    # 작업을 지우면 아래 네 테이블의 딸린 행도 함께 지운다
    result: Mapped['Result | None'] = relationship(back_populates='job', cascade='all, delete-orphan', passive_deletes=True)
    evidence: Mapped[list['Evidence']] = relationship(back_populates='job', cascade='all, delete-orphan', passive_deletes=True)
    failure: Mapped['Failure | None'] = relationship(back_populates='job', cascade='all, delete-orphan', passive_deletes=True)
    review: Mapped['Review | None'] = relationship(back_populates='job', cascade='all, delete-orphan', passive_deletes=True)


class Result(Base):
    """판정 결과 — 점수가 나온 작업(완료·판단 보류) 1건 (api.ts DoneResult / HoldResult)"""

    __tablename__ = 'results'

    job_id: Mapped[str] = mapped_column(ForeignKey('jobs.id', ondelete='CASCADE'), primary_key=True)
    verdict: Mapped[str] = mapped_column(String(8))  # 'real' | 'fake' | 'hold'
    score: Mapped[float | None] = mapped_column(Float, default=None)  # S. 판단 보류면 None
    p_model: Mapped[float] = mapped_column(Float)
    p_model_std: Mapped[float] = mapped_column(Float)
    p_rppg: Mapped[float] = mapped_column(Float)
    w: Mapped[float] = mapped_column(Float)
    axis_gap: Mapped[float] = mapped_column(Float)  # |P_model − P_rppg|
    rppg_low_contribution: Mapped[bool] = mapped_column(Boolean)  # SQI < 하한
    # P_rppg가 분류기 없이 임시로 P_model 값을 쓴 결과인지(5단계 전). 4단계에서 추가한 칸(db.py _ADDED_COLUMNS)
    p_rppg_provisional: Mapped[bool] = mapped_column(Boolean, default=False)
    sqi: Mapped[float] = mapped_column(Float)
    sqi_grade: Mapped[str] = mapped_column(String(8))  # 'good' | 'fair' | 'poor'
    sqi_components: Mapped[dict] = mapped_column(JSON)  # face_pixels, compression, illumination, motion
    roi_bpm: Mapped[dict] = mapped_column(JSON)  # forehead, left_cheek, right_cheek (추정 실패면 null)
    # 판정할 때 쓴 임계값. 나중에 임계값이 바뀌어도 그때 어떤 기준으로 판정했는지 남기려고 결과와 함께 저장한다
    thresholds: Mapped[dict] = mapped_column(JSON)
    interpretation: Mapped[str] = mapped_column(Text)  # 판정 카드의 자연어 해석

    job: Mapped[Job] = relationship(back_populates='result')


class Evidence(Base):
    """근거 데이터 — 작업 1건 × 얼굴 부위 1개 ('all' | 'forehead' | 'left_cheek' | 'right_cheek')"""

    __tablename__ = 'evidence'

    job_id: Mapped[str] = mapped_column(ForeignKey('jobs.id', ondelete='CASCADE'), primary_key=True)
    roi: Mapped[str] = mapped_column(String(16), primary_key=True)
    # api.ts EvidenceResponse 전체 (파형, 스펙트럼, 윈도우 BPM, 모델 프로파일, 특징 표, 두 축 요약 …)
    data: Mapped[dict] = mapped_column(JSON)

    job: Mapped[Job] = relationship(back_populates='evidence')


class Failure(Base):
    """분석 불가 사유 — 분석이 중단된 작업 1건 (api.ts FailureInfo)"""

    __tablename__ = 'failures'

    job_id: Mapped[str] = mapped_column(ForeignKey('jobs.id', ondelete='CASCADE'), primary_key=True)
    code: Mapped[str] = mapped_column(String(32))  # FACE_NOT_DETECTED | VIDEO_TOO_SHORT | FILE_CORRUPTED | UNKNOWN
    title: Mapped[str] = mapped_column(String(255))
    stopped_stage: Mapped[str] = mapped_column(String(16))  # upload | preprocess | model | rppg | fusion
    stopped_stage_index: Mapped[int] = mapped_column(Integer)  # 1부터
    checks: Mapped[list] = mapped_column(JSON)  # [{label, measured, criterion, passed}]
    suggestions: Mapped[list] = mapped_column(JSON)  # 권장 조치 문장들

    job: Mapped[Job] = relationship(back_populates='failure')


class Review(Base):
    """검토자 판단 — 판단 보류 작업 1건. [수정]하면 덮어쓴다 (api.ts Review)"""

    __tablename__ = 'reviews'

    job_id: Mapped[str] = mapped_column(ForeignKey('jobs.id', ondelete='CASCADE'), primary_key=True)
    decision: Mapped[str] = mapped_column(String(24))  # 'real' | 'fake' | 'needs_more_review'
    reason: Mapped[str] = mapped_column(Text, default='')
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    job: Mapped[Job] = relationship(back_populates='review')
