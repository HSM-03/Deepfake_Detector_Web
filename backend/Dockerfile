FROM python:3.10-slim

# dlib 컴파일에 필요한 빌드 도구(build-essential, cmake)와 OpenCV 실행에 필요한 라이브러리
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 라이브러리 목록이 바뀌지 않으면 다음 빌드 때 이 단계를 다시 하지 않는다(dlib 컴파일이 오래 걸리므로)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 웹 서버·작업 큐 라이브러리. dlib 설치 다음에 두어서, 이 목록이 바뀌어도 위의 dlib 층은 다시 만들지 않는다
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY . .