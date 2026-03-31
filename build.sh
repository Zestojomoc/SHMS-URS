#!/bin/bash

# Update the package list
echo "Updating package lists..."
apt-get update -y

# Install necessary system dependencies for Python packages like scipy
echo "Installing system dependencies..."
apt-get install -y \
    gfortran \
    build-essential \
    libatlas-base-dev \
    libopenblas-dev \
    liblapack-dev \
    python3-dev \
    libpq-dev \
    curl

# Install virtual environment package if not already available
echo "Installing virtual environment package..."
apt-get install -y python3-venv

# Set up Python virtual environment
echo "Setting up virtual environment..."
python3 -m venv /venv

# Activate the virtual environment
echo "Activating virtual environment..."
source /venv/bin/activate

# Upgrade pip to the latest version
echo "Upgrading pip..."
pip install --upgrade pip

# Install the Python dependencies from requirements.txt
echo "Installing Python dependencies..."
pip install -r /app/requirements.txt

# Collect static files
echo "Collecting static files..."
python /app/manage.py collectstatic --noinput

# Apply database migrations
echo "Applying database migrations..."
python /app/manage.py migrate --noinput

# Run the NFD Processor (as requested)
echo "Running NFD processor..."
python /app/core/nfd_processor.py

# Deactivate the virtual environment
deactivate

echo "Build completed successfully!"