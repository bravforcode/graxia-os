FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    age \
    curl \
    docker.io \
    g++ \
    gcc \
    libpq-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN groupadd --gid 1001 app \
    && useradd --uid 1001 --gid 1001 --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/logs /app/backups \
    && chown -R app:app /app

USER 1001:1001
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
