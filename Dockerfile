FROM python:3.12-slim-trixie

LABEL maintainer="mkhaikin@yandex.ru"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    libcap2-bin iputils-ping

ADD https://astral.sh/uv/install.sh /uv-installer.sh

RUN sh /uv-installer.sh && rm /uv-installer.sh

ENV PATH="/root/.local/bin/:$PATH"
ENV UV_NO_DEV=1
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN groupadd --system appgroup && \
    useradd --system --gid appgroup --create-home appuser

RUN chown -R appuser:appgroup /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked

RUN setcap cap_net_raw+ep /usr/local/bin/python3.12 && \
    if [ -f /app/.venv/bin/python ]; then setcap cap_net_raw+ep $(readlink -f /app/.venv/bin/python); fi

COPY ./prepare.sh /app/prepare/prepare.sh
RUN chmod +x /app/prepare/prepare.sh

USER appuser

ENV PATH="/app/.venv/bin:$PATH"

COPY ./migrations /app/migrations
COPY ./src /app
