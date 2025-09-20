# docker run --rm -p 8080:8080 api-builder-webapp:latest
ARG BASE_IMAGE=webapp-cache:latest
FROM ${BASE_IMAGE}

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./app.py
COPY src ./src
COPY secrets ./secrets
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY docs ./docs
COPY scripts ./scripts

ENV PORT=8080
ENV PYTHONPATH=/app

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
