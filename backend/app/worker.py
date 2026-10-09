"""
Celery 워커 — 오래 걸리는 분석을 API 서버와 분리해서 처리한다.

실행(컨테이너 안): celery -A app.worker worker --loglevel=info --concurrency=1
"""
from celery import Celery
from celery.signals import worker_init

from . import config
from .db import init_db

celery_app = Celery('deepfake', broker=config.REDIS_URL, backend=config.REDIS_URL)
celery_app.conf.update(
    # 분석 하나가 CPU를 다 쓰므로, 워커가 작업을 미리 여러 개 가져가 쌓아 두지 않게 한다
    worker_prefetch_multiplier=1,
    # 작업이 끝난 뒤에 '받았음'을 알린다. 워커가 도중에 죽으면 작업이 큐로 돌아간다
    task_acks_late=True,
    broker_connection_retry_on_startup=True,
    # 워커가 시작할 때 불러올 작업 모듈 (tasks.py가 이 파일을 import하므로, 여기서 직접 import하지 않는다)
    include=['app.tasks'],
)


@worker_init.connect
def _prepare_db(**_kwargs) -> None:
    """워커가 시작될 때 한 번: API 서버보다 먼저 떠도 DB 테이블이 준비되게 한다"""
    init_db()


@celery_app.task(name='ping')
def ping() -> str:
    """연결 확인용: API → Redis → 워커 → Redis → API로 한 바퀴 돌면 'pong'이 돌아온다"""
    return 'pong'
