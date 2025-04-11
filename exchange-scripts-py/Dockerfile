# Use an official Python runtime as the base image
FROM python:3.9

# Set the working directory to /app
WORKDIR /app

COPY fix/requirements.txt /app/fix/requirements.txt
COPY fix_md/requirements.txt /app/fix_md/requirements.txt   

# Install any needed packages specified in requirements.txt only for prod 
# RUN pip install --no-cache-dir -r fix/requirements.txt
# RUN pip install --no-cache-dir -r fix_md/requirements.txt

## Dev install 
RUN pip install -r fix/requirements.txt
RUN pip install -r fix_md/requirements.txt


# Copy the rest of the application code to /app
COPY . .

# # Define the default command to run your app
# ENTRYPOINT ["sh", "-c", "sleep infinity"]