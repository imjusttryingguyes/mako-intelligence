FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/src
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
RUN pip install --no-cache-dir . && \
    groupadd --system mako && useradd --system --gid mako --home /app mako
USER mako
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "mako.main:app", "--host", "0.0.0.0", "--port", "8000"]
