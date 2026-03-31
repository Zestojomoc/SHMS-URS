# Use the official Python image from Docker Hub
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the project files into the container
COPY . /app/

# Install system dependencies for building packages like scipy
RUN apt-get update && apt-get install -y \
    gfortran \
    build-essential \
    libopenblas-dev \
    liblapack-dev \
    python3-dev \
    libpq-dev \
    curl \
    libatlas3-base

# Install virtual environment package if not already available
RUN apt-get install -y python3-venv

# Set up the virtual environment
RUN python3 -m venv /venv

# Activate the virtual environment and install Python dependencies
RUN /venv/bin/pip install --upgrade pip
RUN /venv/bin/pip install -r /app/requirements.txt

# Collect static files
RUN /venv/bin/python /app/manage.py collectstatic --noinput

# Apply database migrations
RUN /venv/bin/python /app/manage.py migrate --noinput

# Expose port 8000 (the default port Django runs on)
EXPOSE 8000

# Start the Django development server
CMD ["/venv/bin/python", "/app/manage.py", "runserver", "0.0.0.0:8000"]