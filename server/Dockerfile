# Builder
FROM python:3.13-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock /app/
RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
RUN pip install --no-cache-dir uvicorn
COPY . /app/
RUN pip install --no-cache-dir .

# Runtime
FROM python:3.13-slim
WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["python", "-m", "app.main"]