# Stage 1: Build the application
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for OpenCV and other libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose the port the app runs on
EXPOSE 5000

# Run the application using a production-ready server
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]