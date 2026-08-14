
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

# Copy dependency manifest from the build context (project root)
COPY requirements.txt ./

# Copy alembic config so migrations are available inside the image
COPY alembic.ini ./

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend source
COPY backend ./backend

# Copy and make entrypoint executable
COPY backend/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]

