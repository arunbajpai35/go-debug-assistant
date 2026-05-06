# --- builder: compiles wheels for c-extension deps in a throwaway image ---
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel -r requirements.txt -w /wheels


# --- runtime: no compiler, no headers; just python + the prebuilt wheels ---
FROM python:3.12-slim AS runtime

ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
ENV GIT_SHA=$GIT_SHA \
    BUILD_DATE=$BUILD_DATE \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libpq5 is the runtime libpq. no -dev headers, no gcc.
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r app && useradd -r -g app -d /app -s /usr/sbin/nologin app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt && rm -rf /wheels

COPY backend ./backend
COPY alembic.ini ./alembic.ini

USER app
EXPOSE 8000

CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000"]
