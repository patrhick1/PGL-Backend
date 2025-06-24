# Use Python 3.9 slim image as base
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml poetry.lock* requirements.txt* ./

# Install Python dependencies
# First try poetry, fallback to requirements.txt
RUN pip install --no-cache-dir poetry==1.8.2 && \
    (poetry config virtualenvs.create false && \
     poetry install --no-interaction --no-ansi --only main) || \
    (pip install --no-cache-dir -r requirements.txt)

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose the port your app runs on
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api-status || exit 1

# Run the application
CMD ["uvicorn", "podcast_outreach.main:app", "--host", "0.0.0.0", "--port", "8000"]