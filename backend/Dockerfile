FROM python:3.12.4-slim

RUN groupadd -r pepper && useradd -r -g pepper pepper

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY agent_ids.json ./agent_ids.json

ENV PEPPER_DATA_DIR=/var/lib/pepper
ENV PEPPER_AGENT_IDS=/app/agent_ids.json

RUN mkdir -p /var/lib/pepper && chown -R pepper:pepper /var/lib/pepper /app
VOLUME /var/lib/pepper

USER pepper
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
