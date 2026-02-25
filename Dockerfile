# Railway용 Dockerfile — pyppeteer + 한국어 폰트 지원
FROM python:3.11-slim

# ─── 시스템 패키지 ────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y \
    # Chromium (pyppeteer용) — Debian Bookworm
    chromium \
    # 한국어 폰트 (Noto CJK)
    fonts-noto-cjk \
    fonts-noto-cjk-extra \
    # Chromium 실행 필수 의존성 (Bookworm 기준)
    wget \
    ca-certificates \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libgbm-dev \
    libasound2 \
    libxshmfence1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libpango-1.0-0 \
    libcairo2 \
    --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ─── pyppeteer에 Chromium 경로 지정 ──────────────────────────────────────
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

# ─── Python 작업 디렉토리 ────────────────────────────────────────────────
WORKDIR /app

# ─── 패키지 설치 ──────────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── 앱 복사 ──────────────────────────────────────────────────────────────
COPY . .

# ─── 실행 ────────────────────────────────────────────────────────────────
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
