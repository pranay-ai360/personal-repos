# Use the official Bitnami Spark image as the base image
FROM bitnami/spark:latest

# Set environment variables for Spark and Java
ENV SPARK_HOME=/opt/bitnami/spark
ENV PATH=$SPARK_HOME/bin:$PATH

# Copy the entrypoint script into the container
COPY entrypoint.sh /opt/bitnami/spark/entrypoint.sh

# Set the permissions to make the script executable (with root permissions during build)
USER root
RUN chmod +x /opt/bitnami/spark/entrypoint.sh

# Set the entrypoint to the script
ENTRYPOINT ["/opt/bitnami/spark/entrypoint.sh"]

# Set the default command (Spark master mode) if not specified
CMD ["/opt/bitnami/spark/bin/spark-class", "org.apache.spark.deploy.master.Master"]