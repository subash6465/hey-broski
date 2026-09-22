FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/api/app ./app

EXPOSE 8000

RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /data/heybroski && chown -R app:app /app /data/heybroski

USER app

HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
