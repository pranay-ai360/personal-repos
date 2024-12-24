#!/bin/bash

# Start Cassandra in the background
/entrypoint.sh cassandra &

# Wait for Cassandra to start up and be ready
echo "Waiting for Cassandra to start..."
sleep 30  # Sleep for 30 seconds to allow Cassandra to start properly

# Create the keyspace if it doesn't exist
echo "Creating keyspace 'default'..."
cqlsh -e "CREATE KEYSPACE IF NOT EXISTS default WITH REPLICATION = {'class' : 'SimpleStrategy', 'replication_factor' : 1};"

# Wait for Cassandra to finish initializing and then bring it to the foreground
wait