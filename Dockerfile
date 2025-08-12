FROM python:3.10-slim

WORKDIR /app


# Install Poetry with increased timeout
RUN pip install --no-cache-dir --default-timeout=100 poetry

# Copy only pyproject.toml and poetry.lock first for better Docker caching
COPY pyproject.toml poetry.lock* ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --only main

# Copy the rest of the code
COPY . .

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]