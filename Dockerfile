# docker run --rm -p 8080:8080 object-detection-data-webapp:latest
ARG BASE_IMAGE=webapp-cache:latest
FROM ${BASE_IMAGE}

WORKDIR /app

# Install Node.js 20 for Gradio SSR support
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && install -d -m 0755 /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/*

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
