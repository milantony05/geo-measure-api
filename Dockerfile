FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies FIRST. Docker caches each step, so as long as
# requirements.txt doesn't change, rebuilds skip this slow step.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Then copy the application code (this changes often).
COPY app ./app

# Run as a non-root user and keep the database in a dedicated /data folder.
RUN useradd --create-home appuser \
    && mkdir /data \
    && chown appuser /data
USER appuser
ENV DATABASE_URL=sqlite:////data/geo.db

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]