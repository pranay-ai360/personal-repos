# Use the official Python 3 image with pip included
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy only requirements first for better caching
COPY requirements.txt .

# Upgrade pip and install dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of the application code
COPY . .

# Specify the default command (modify as needed)
CMD ["python", "cb-socket.py"]