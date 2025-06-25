# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory to parent of podcast_outreach
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
COPY podcast_outreach/requirements.txt ./

# Install Python dependencies
# Use --no-deps for conflicting packages and install them separately
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt || \
    (grep -v "google-generativeai\|langchain-google-genai" requirements.txt > requirements_filtered.txt && \
     pip install --no-cache-dir -r requirements_filtered.txt && \
     pip install --no-cache-dir langchain-google-genai google-generativeai)

# Copy application code
COPY podcast_outreach/ ./podcast_outreach/

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Copy startup script for production deployments
COPY --chown=appuser:appuser podcast_outreach/startup.sh /app/
RUN chmod +x /app/startup.sh

# Switch to non-root user
USER appuser

# Expose the port your app runs on
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api-status || exit 1

# Default command - can be overridden for production to use startup.sh
# For local development:
CMD ["uvicorn", "podcast_outreach.main:app", "--host", "0.0.0.0", "--port", "8000"]

# For production deployments on Render or similar platforms:
# Override the CMD in your deployment configuration to use:
# CMD ["/app/startup.sh"]