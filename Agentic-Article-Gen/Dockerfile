FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directory for SQLite database
RUN mkdir -p tmp

# Expose port
EXPOSE 8080

# Use environment variables
ENV REDIS_HOST=${REDIS_HOST}
ENV REDIS_PORT=${REDIS_PORT}
ENV OPENAI_API_KEY=${OPENAI_API_KEY}

# Command to run the application
CMD exec uvicorn blog_post_generator_api:app --host 0.0.0.0 --port 8080