FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Tashkent

RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --create-home ferma

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=ferma:ferma . .
RUN mkdir -p data/checkins static/snapshots && chown -R ferma:ferma data static/snapshots

USER ferma
EXPOSE 8085
CMD ["gunicorn", "main:app", "--workers", "2", "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8085", "--timeout", "120", "--access-logfile", "-"]
