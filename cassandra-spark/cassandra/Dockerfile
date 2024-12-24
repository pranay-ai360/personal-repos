# Use the official Cassandra image as the base image
FROM cassandra:latest

# Copy the custom entrypoint script into the container
COPY entrypoint.sh /entrypoint.sh

# Make the script executable
RUN chmod +x /entrypoint.sh

# Set the entrypoint to our custom script
ENTRYPOINT ["/entrypoint.sh"]