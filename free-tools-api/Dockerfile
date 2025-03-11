FROM python:3.9

# Install system dependencies
RUN apt-get update && apt-get install -y ffmpeg redis-server supervisor

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project files
COPY . .

# Copy the supervisor config file into the container
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose the port for FastAPI
EXPOSE 8000

# Command to start supervisord
CMD ["/usr/bin/supervisord"]
