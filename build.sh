#!/bin/bash

# Update package lists
echo "Updating package lists..."
apt-get update -y

# Install necessary build tools and compilers for Python packages like scipy
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

# Install the Python dependencies
echo "Installing Python dependencies..."
pip install -r /app/requirements.txt

# Deactivate the virtual environment
deactivate

echo "Build completed successfully!"