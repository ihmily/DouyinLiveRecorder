# Stage 1: Build stage - Install required packages and Node.js, ffmpeg
FROM python:3.11-slim AS build-stage

# Set the working directory
WORKDIR /app

# Copy the base-setup.sh file into the container
COPY base-setup.sh /app/base-setup.sh

# Execute base-setup.sh to install the required packages
RUN chmod +x /app/base-setup.sh && /app/base-setup.sh

# Stage 2: Application dependencies - Install Python dependencies
FROM build-stage AS app-dependencies

WORKDIR /app

# Copy necessary files (requirements.txt)
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Stage 3: Final stage - Create a lightweight image for the final product
FROM app-dependencies AS final-stage

WORKDIR /app

# Copy the source code
COPY . /app

# Set the default command for the container
CMD ["python", "main.py"]
