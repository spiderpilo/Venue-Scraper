FROM python:3.13-slim

# System deps for Playwright chromium
RUN apt-get update && apt-get install -y \
    wget curl gnupg \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install chromium && playwright install-deps chromium

COPY src/ src/
COPY models/ models/
COPY run_model_pipeline.py .
COPY scrape_inspect.py .

VOLUME ["/app/data"]

CMD ["python", "run_model_pipeline.py", "--help"]
