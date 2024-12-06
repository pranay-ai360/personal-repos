#!/bin/bash

# Input file containing NAT Gateway IDs
input_file="list.txt"

# Check if the input file exists
if [ ! -f "$input_file" ]; then
    echo "File $input_file not found!"
    exit 1
fi

# Loop through each line in the input file
while read -r line; do
    # Trim whitespace from the line
    line=$(echo "$line" | xargs)

    # Check if the line contains a NAT Gateway ID
    if [[ $line == nat-* ]]; then
        echo "Deleting NAT Gateway ID: $line"
        # Delete the NAT Gateway
        response=$(aws ec2 delete-nat-gateway --nat-gateway-id "$line" 2>&1)
        if [ $? -eq 0 ]; then
            echo "Successfully deleted NAT Gateway ID: $line"
        else
            echo "Failed to delete NAT Gateway ID: $line. Error: $response"
        fi
    fi
done < "$input_file"