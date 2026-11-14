# syntax=docker/dockerfile:1
FROM python:3.13-slim AS build
RUN pip install --no-cache-dir uv==0.13.6
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
# dependencies first, so that they are cached until pyproject.toml / uv.lock change
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.13-slim
# an unprivileged user without a shell or home directory
RUN useradd --system --uid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin bot \
    && mkdir /data /keys && chown bot /data /keys && chmod 700 /data /keys
COPY --from=build /app /app
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/data/blakkisvuohi.sqlite3 \
    KEY_DATABASE_PATH=/keys/keys.sqlite3 \
    MPLCONFIGDIR=/tmp/matplotlib
USER bot
VOLUME /data /keys
CMD ["python", "-m", "blakkisvuohi"]
