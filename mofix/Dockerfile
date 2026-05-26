FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=matchoracle.settings

# Set working directory
WORKDIR /app/mofix

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy project source
COPY . .

# Collect static files (best-effort; won't fail if env vars are missing)
RUN python manage.py collectstatic --noinput || true

# Default command — Railway overrides this per service
CMD ["gunicorn", "matchoracle.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
