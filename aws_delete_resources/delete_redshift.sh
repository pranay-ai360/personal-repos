#!/bin/bash

# Set the region
REGION="ap-southeast-2"

# Get the list of Redshift Serverless workspaces
workspaces=$(aws redshift-serverless list-workspaces --region "$REGION" --query 'workspaces[*].{Id:workspaceId,Name:workspaceName}' --output json)

# Check if the workspaces variable is empty
if [ -z "$workspaces" ] || [ "$workspaces" == "[]" ]; then
    echo "No Redshift Serverless workspaces found in region $REGION."
    exit 0
fi

# Loop through each workspace and delete it
echo "Found the following Redshift Serverless workspaces:"
echo "$workspaces" | jq '.[] | {Id, Name}'

for workspace in $(echo "$workspaces" | jq -c '.[]'); do
    workspace_id=$(echo "$workspace" | jq -r '.Id')
    workspace_name=$(echo "$workspace" | jq -r '.Name')

    echo "Deleting Redshift Serverless workspace: $workspace_name (ID: $workspace_id)"
    
    # Delete the Redshift Serverless workspace
    delete_response=$(aws redshift-serverless delete-workspace --workspace-id "$workspace_id" --region "$REGION" 2>&1)

    if [ $? -eq 0 ]; then
        echo "Successfully deleted Redshift Serverless workspace: $workspace_name (ID: $workspace_id)"
    else
        echo "Failed to delete Redshift Serverless workspace: $workspace_name (ID: $workspace_id). Error: $delete_response"
    fi
done