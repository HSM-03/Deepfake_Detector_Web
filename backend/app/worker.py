"""
Celery 워커 — 오래 걸리는 분석을 API 서버와 분리해서 처리한다.

실행(컨테이너 안): celery -A app.worker worker --loglevel=info --concurrency=1
"""
from celery import Celery
from celery.signals import worker_init, worker_ready

from . import config
from .db import init_db

celery_app = Celery('deepfake', broker=config.REDIS_URL, backend=config.REDIS_URL)
celery_app.conf.update(
    # 분석 하나가 CPU를 다 쓰므로, 워커가 작업을 미리 여러 개 가져가 쌓아 두지 않게 한다
    worker_prefetch_multiplier=1,
    # 작업이 끝난 뒤에 '받았음'을 알린다. 워커가 도중에 죽으면 작업이 큐로 돌아간다
    # (단, Redis는 visibility_timeout(기본 1시간)이 지나야 돌려준다 — 그래서 아래 _resume_interrupted가 바로 다시 넣는다)
    task_acks_late=True,
    broker_connection_retry_on_startup=True,
    # 워커가 시작할 때 불러올 작업 모듈 (tasks.py가 이 파일을 import하므로, 여기서 직접 import하지 않는다)
    include=['app.tasks'],
)


@worker_init.connect
def _prepare_db(**_kwargs) -> None:
    """워커가 시작될 때 한 번: API 서버보다 먼저 떠도 DB 테이블이 준비되게 한다"""
    init_db()


@worker_ready.connect
def _resume_interrupted(**_kwargs) -> None:
    """
    워커가 켜질 때 한 번: DB에 '진행 중'·'대기 중'으로 남은 작업을 다시 큐에 넣는다.
    워커는 하나뿐(동시 1개)이라, 지금 막 켜진 시점에 '진행 중'인 작업은 이전 워커가 분석 도중 꺼진 것이다
    (docker compose restart worker는 10초 기다린 뒤 강제로 끈다). 그대로 두면 Redis가 1시간 뒤에야 다시 줘서
    진행 화면이 그동안 멈춰 있다. 다시 넣은 작업은 tasks.py가 남은 기록을 지우고 처음부터 분석하고,
    나중에 원래 메시지가 다시 와도 이미 끝난 작업이라 건너뛴다.
    '대기 중' 작업은 Redis가 함께 꺼지면(WSL 종료 등) 큐의 메시지가 사라져 영영 대기 중으로 남으므로 같이 다시 넣는다.
    메시지가 남아 있었다면 같은 작업이 두 번 오지만, 두 번째는 이미 끝난 작업이라 건너뛴다.
    워커를 여러 개 띄우게 되면 다른 워커가 실제로 처리 중인 작업까지 다시 넣으므로 이 방식을 바꿔야 한다.
    """
    import logging

    from .db import SessionLocal
    from .models import Job

    with SessionLocal() as db:
        for job in db.query(Job).filter(Job.state.in_(('running', 'queued'))).order_by(Job.created_at).all():
            job.celery_task_id = celery_app.send_task('analyze_video', args=[job.id]).id
            reason = '이전 워커가 분석 도중 꺼져' if job.state == 'running' else '대기 중이던 작업이라'
            logging.getLogger('deepfake.tasks').info('[%s] %s 다시 큐에 넣음', job.id, reason)
        db.commit()


@celery_app.task(name='ping')
def ping() -> str:
    """연결 확인용: API → Redis → 워커 → Redis → API로 한 바퀴 돌면 'pong'이 돌아온다"""
    return 'pong'
