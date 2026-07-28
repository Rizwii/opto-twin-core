FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/twin_engine /app/services/twin_engine

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/services/twin_engine

EXPOSE 8000

CMD ["uvicorn", "services.twin_engine.main:app", "--host", "0.0.0.0", "--port", "8000"]