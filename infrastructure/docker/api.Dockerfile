FROM python:3.14-slim AS runtime
ARG NEURORESECT_GIT_COMMIT=unavailable
ENV NEURORESECT_GIT_COMMIT=$NEURORESECT_GIT_COMMIT
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.lock /app/requirements.lock
COPY packages/neurocore /app/packages/neurocore
COPY apps/api /app/apps/api
RUN pip install -c /app/requirements.lock /app/packages/neurocore '/app/apps/api[worker]'
COPY workers /app/workers
COPY configs /app/configs
RUN useradd --create-home --uid 10001 researcher && mkdir -p /app/data /app/artifacts && chown -R researcher:researcher /app/data /app/artifacts
USER researcher
EXPOSE 8000
CMD ["uvicorn", "neuroresect_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
