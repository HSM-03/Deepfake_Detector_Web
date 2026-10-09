"""
SQLite 연결과 테이블 생성.

API 서버와 워커가 같은 DB 파일을 동시에 쓰므로 WAL 모드를 켠다.
테이블은 시작할 때 없는 것만 만든다(create_all). 구조를 바꾸면 개발 중에는 볼륨을 지우고 새로 만든다:
  docker compose down -v

확인용 실행(컨테이너 안): python -m app.db
"""
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config


class Base(DeclarativeBase):
    """모든 테이블 클래스(models.py)의 부모"""


engine = create_engine(
    f'sqlite:///{config.DB_PATH}',
    # 같은 연결을 여러 스레드(FastAPI 요청 처리)에서 써도 되게 한다
    connect_args={'check_same_thread': False},
)


@event.listens_for(engine, 'connect')
def _sqlite_pragmas(dbapi_connection, _record) -> None:
    """연결이 새로 생길 때마다 SQLite 설정을 적용한다"""
    cursor = dbapi_connection.cursor()
    cursor.execute('PRAGMA journal_mode=WAL')  # 읽기와 쓰기를 동시에 (API가 읽는 중에 워커가 써도 됨)
    cursor.execute('PRAGMA busy_timeout=5000')  # 잠겨 있으면 바로 오류 내지 말고 최대 5초 기다림
    cursor.execute('PRAGMA synchronous=NORMAL')  # WAL에서 권장되는 저장 방식
    cursor.execute('PRAGMA foreign_keys=ON')  # 작업을 지우면 딸린 결과·근거도 함께 지워지게
    cursor.close()


# 요청 하나, 작업 하나마다 SessionLocal()로 세션을 열고 끝나면 닫는다
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """데이터 폴더와 업로드 폴더를 만들고, 없는 테이블을 만든다. API 서버와 워커가 시작할 때 부른다"""
    from . import models  # noqa: F401 — 테이블 클래스들을 Base에 등록하기 위해 불러온다

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)


def _print_status() -> None:
    """DB 파일 위치, 저널 모드, 테이블·열 목록을 출력한다"""
    with engine.connect() as connection:
        mode = connection.execute(text('PRAGMA journal_mode')).scalar()
    print(f'DB 파일: {config.DB_PATH}')
    print(f'저널 모드: {mode}')
    for table in inspect(engine).get_table_names():
        columns = ', '.join(column['name'] for column in inspect(engine).get_columns(table))
        print(f'  {table}: {columns}')


if __name__ == '__main__':
    # 'python -m app.db'로 실행하면 이 파일이 __main__으로 한 번 더 읽혀서, models.py가 등록하는 쪽(app.db)과
    # 여기의 Base가 서로 다른 객체가 된다. 그래서 정식 모듈(app.db)의 함수를 불러 쓴다.
    from app import db

    db.init_db()
    db._print_status()
