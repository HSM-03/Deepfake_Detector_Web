"""
FastAPI 앱 — 프론트엔드가 부르는 /api/* 를 처리한다.

실행(컨테이너 안): uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
API 문서(자동 생성): http://localhost:8000/docs
"""
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from analysis import settings as analysis_settings

from . import config
from .api import router
from .db import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """서버가 시작될 때 한 번: 데이터 폴더와 DB 테이블을 준비한다"""
    init_db()
    yield


app = FastAPI(title='딥페이크 탐지기 API', version='0.1.0', lifespan=lifespan)
app.include_router(router)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, error: RequestValidationError) -> JSONResponse:
    """
    잘못된 입력(422). FastAPI 기본 응답은 detail이 목록이라, 프론트엔드가 기대하는 { "detail": "문장" } 형태로 바꾼다
    (frontend/src/api/client.ts의 getErrorMessage는 문자열 detail만 화면에 보여 준다).
    """
    first = error.errors()[0] if error.errors() else {}
    where = '.'.join(str(part) for part in first.get('loc', [])[1:])
    message = first.get('msg', '입력값이 올바르지 않습니다')
    return JSONResponse(status_code=422, content={'detail': f'입력값이 올바르지 않습니다: {where} — {message}'})


@app.get('/api/health')
def health() -> dict:
    """서버 상태 확인: Redis 연결과 더미 분석 여부를 함께 알려 준다"""
    try:
        redis_ok = bool(redis.Redis.from_url(config.REDIS_URL, socket_timeout=2).ping())
    except redis.RedisError:
        redis_ok = False
    return {
        'status': 'ok',
        'redis': redis_ok,
        'dummy_main_model': analysis_settings.USE_DUMMY_MAIN_MODEL,
        'dummy_rppg': analysis_settings.USE_DUMMY_RPPG,
    }
