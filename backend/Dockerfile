FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Cloud Run 會注入 $PORT；本機 compose 我們會覆寫成 8000
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
