FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/ingestion /app/services/ingestion

ENV PYTHONUNBUFFERED=1

CMD ["python", "services/ingestion/main.py"]