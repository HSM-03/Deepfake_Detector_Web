"""
서버 설정 — 경로·주소는 환경변수로 받는다(docker-compose.yml에서 넘겨준다).
분석·판정에 관한 값(프레임 수, 임계값, 더미 분석 여부 등)은 여기가 아니라 analysis/settings.py에 있다.
"""
import os
from pathlib import Path

# DB 파일과 업로드 영상을 두는 폴더. compose에서 Docker 볼륨을 이 위치에 연결한다
# (D: 드라이브에 두면 WSL을 거치며 파일 잠금이 불안정해 SQLite가 'database is locked'를 낼 수 있다)
DATA_DIR = Path(os.environ.get('DATA_DIR', '/var/lib/deepfake'))
DB_PATH = DATA_DIR / 'deepfake.sqlite3'
UPLOAD_DIR = DATA_DIR / 'uploads'

# 업로드 제한 (화면설계서 SCR-01: MP4·MOV·AVI·WebM, 최대 500MB). 프론트엔드도 같은 검사를 하지만 서버에서 한 번 더 막는다
ALLOWED_EXTENSIONS = {'.mp4', '.mov', '.avi', '.webm'}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024

# Celery가 작업을 주고받는 통로이자 진행률을 기록하는 곳. 'redis'는 compose 안의 Redis 서비스 이름이다
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
