#Dockerfile for Gideon
# Use the official Python image from the Docker Hub
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container at /app
# Assuming your Dockerfile is in the root of the gideon project
COPY ./src ./src

# Expose dashboard port (configurable via DASHBOARD_PORT env var, default 8080)
EXPOSE 8080

CMD ["python", "-m", "src"]