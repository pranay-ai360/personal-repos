# Use an official Python runtime as the base image
FROM python:3.9

# Set the working directory to /app
WORKDIR /app

# Install any needed packages specified in requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code to /app
COPY . .


# # Define the default command to run your app
# ENTRYPOINT ["sh", "-c", "sleep infinity"]