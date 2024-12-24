#!/bin/bash

# Spark-Cassandra Connector version
SPARK_CASSANDRA_VERSION="3.0.0"
SPARK_CASSANDRA_CONNECTOR="com.datastax.spark:spark-cassandra-connector_2.12:${SPARK_CASSANDRA_VERSION}"

# Install the Spark Cassandra Connector using --packages option
echo "Setting up Spark Cassandra Connector version ${SPARK_CASSANDRA_VERSION}"

# Add the Spark Cassandra Connector to the Spark configuration
export SPARK_SUBMIT_OPTIONS="--packages ${SPARK_CASSANDRA_CONNECTOR}"

# Connect to Cassandra and create the keyspace if it doesn't exist
echo "Creating Cassandra keyspace 'default' if it does not exist..."

# Connect to Cassandra via cqlsh and create the keyspace
cqlsh -e "CREATE KEYSPACE IF NOT EXISTS default WITH REPLICATION = {'class' : 'SimpleStrategy', 'replication_factor' : 1};"

# Start Spark Master or Worker depending on the environment
if [ "$SPARK_MODE" == "master" ]; then
    echo "Starting Spark Master..."
    exec /opt/bitnami/spark/bin/spark-class org.apache.spark.deploy.master.Master
elif [ "$SPARK_MODE" == "worker" ]; then
    echo "Starting Spark Worker..."
    exec /opt/bitnami/spark/bin/spark-class org.apache.spark.deploy.worker.Worker --master spark://spark-master:7077
else
    echo "Unknown Spark mode: $SPARK_MODE. Exiting..."
    exit 1
fi