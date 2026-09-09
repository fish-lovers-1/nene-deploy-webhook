FROM python:3.14-alpine

WORKDIR /app

RUN apk add --no-cache docker-cli docker-cli-compose

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev

COPY main.py ./

CMD ["sh", "-c", "echo \"$GHCR_TOKEN\" | docker login ghcr.io -u \"$GHCR_USERNAME\" --password-stdin && exec uv run uvicorn main:app --host 0.0.0.0 --port 8000"]

