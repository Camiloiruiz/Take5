# Use an official Python runtime based on Debian Bullseye (Debian 11)
FROM python:3.9-slim-bullseye

# Set the working directory in the container
WORKDIR /app

# Install system dependencies needed for psycopg2 (PostgreSQL adapter), git, wget, unzip, and netcat
RUN apt-get update --fix-missing --allow-releaseinfo-change || \
    apt-get update --fix-missing --allow-releaseinfo-change && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        git \
        wget \
        unzip \
        netcat-traditional && \
    rm -rf /var/lib/apt/lists/*

# Install ngrok separately
RUN wget https://bin.equinox.io/c/4VmDzA7iaHb/ngrok-stable-linux-amd64.zip -O ngrok.zip && \
    unzip ngrok.zip && \
    mv ngrok /usr/local/bin/ngrok && \
    chmod +x /usr/local/bin/ngrok && \
    rm ngrok.zip

# Copy the current directory contents into the container at /app
COPY . /app

# Fix line endings and make the wait-for-it script executable
RUN sed -i 's/\r$//' /app/wait-for-it.sh && \
    chmod +x /app/wait-for-it.sh

# Install any needed Python packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port your Flask/Twilio app will run on (e.g., 5000)
EXPOSE 5000

# Default command to run the application (will be overridden by docker-compose)
CMD ["python", "app.py"]