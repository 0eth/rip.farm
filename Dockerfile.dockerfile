# Use official Python image as base
FROM python:3.11-slim

# Install required dependencies for Chromium
RUN apt-get update && apt-get install -y \
    chromium chromium-driver \
    build-essential \
    curl \
    unzip \
    wget \
    gnupg \
    libnss3 \
    libgconf-2-4 \
    libxss1 \
    libasound2 \
    libx11-xcb1 \
    fonts-liberation \
    libappindicator3-1 \
    xdg-utils \
    --no-install-recommends && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set environment variable for Chromium path
ENV CHROME_BIN=/usr/bin/chromium

# Set working directory
WORKDIR /app

# Copy your app code
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 10000

# Start the Flask app using gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]
