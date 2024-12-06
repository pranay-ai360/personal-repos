#!/bin/bash

# Output file
output_file="list.txt"

# Clear the output file if it exists
> "$output_file"

# List of regions
regions=(
    "ap-south-1"  # Asia Pacific (Mumbai)
    "ap-southeast-2"  # Asia Pacific (Sydney)
    "ap-northeast-1"  # Asia Pacific (Tokyo)
    "us-east-1"  # US East (N. Virginia)
    "us-west-2"  # US West (Oregon)
)

# Loop through each region and get NAT Gateways
for region in "${regions[@]}"; do
    echo "Fetching NAT Gateways in region: $region"
    nat_gateway_ids=$(aws ec2 describe-nat-gateways --region "$region" --query 'NatGateways[*].NatGatewayId' --output text)
    
    if [ -n "$nat_gateway_ids" ]; then
        echo "NAT Gateway IDs in $region:" >> "$output_file"
        echo "$nat_gateway_ids" >> "$output_file"
        echo "------------------------------------"
    else
        echo "No NAT Gateways found in $region." >> "$output_file"
    fi
done

echo "NAT Gateway IDs saved to $output_file."