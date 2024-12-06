#!/bin/bash

# Set variables for region, workgroup name, and namespace details
REGION="ap-southeast-2"
WORKGROUP_NAME="default-workgroup"  # Change this if your workgroup name is different
NAMESPACE_ID="9c88c571-5a66-497f-9a37-382e038de112"
NAMESPACE_NAME="default-namespace"   # Change this if your namespace name is different

# Function to delete the workgroup
delete_workgroup() {
    echo "Deleting Redshift Serverless workgroup: $WORKGROUP_NAME"
    
    # Attempt to delete the workgroup
    delete_response=$(aws redshift-serverless delete-workgroup --workgroup-name "$WORKGROUP_NAME" --region "$REGION" 2>&1)
    
    if [ $? -eq 0 ]; then
        echo "Successfully deleted workgroup: $WORKGROUP_NAME"
    else
        echo "Failed to delete workgroup: $WORKGROUP_NAME. Error: $delete_response"
        exit 1  # Exit if the workgroup deletion fails
    fi
}

# Function to delete the namespace
delete_namespace() {
    echo "Deleting Redshift Serverless namespace: $NAMESPACE_NAME"
    
    # Attempt to delete the namespace
    delete_response=$(aws redshift-serverless delete-namespace --namespace-id "$NAMESPACE_ID" --namespace-name "$NAMESPACE_NAME" --region "$REGION" 2>&1)
    
    if [ $? -eq 0 ]; then
        echo "Successfully deleted namespace: $NAMESPACE_NAME"
    else
        echo "Failed to delete namespace: $NAMESPACE_NAME. Error: $delete_response"
    fi
}

# Main script execution
echo "Workgroup Configuration:"
echo "Base Capacity: 128"
echo "Enhanced VPC Routing: false"
echo "Publicly Accessible: true"
echo "Security Group IDs: sg-077cd5294a90acd57"
echo "Namespace Name: $NAMESPACE_NAME"

# Delete the workgroup and then the namespace
delete_workgroup
delete_namespace