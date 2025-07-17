# Use official Python image as base
FROM python:3.11-slim

# Install required dependencies for Chromium (no webdriver-manager here)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libgdk-pixbuf2.0-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    wget \
    curl \
    unzip \
    gnupg \
    --no-install-recommends && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set environment variable for Chromium path
ENV CHROME_BIN=/usr/bin/chromium

# Set working directory
WORKDIR /app

# Copy your app code
COPY . .

# Install Python dependencies including selenium and webdriver-manager
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 10000

# Start the Flask app using gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]
