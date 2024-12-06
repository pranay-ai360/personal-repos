#!/bin/bash

# Set the region
REGION="ap-southeast-2"

# List of resource ARNs to delete
resources=(
    "arn:aws:iam::370296042006:policy/AWS679f53fac002430cb0da5b7982bd22872D164C4"  # Example IAM Policy ARN
    "arn:aws:iam::370296042006:policy/RIVWebAPPRIVWebAppRoleDefaultPolicyF5A64D0D"
    "arn:aws:iam::370296042006:role/RIVWebAPPRIVWebAppmainE864ED78"
    "arn:aws:amplify:ap-southeast-2:370296042006:apps/d1mmnmdaaosebz/branches/main"  # Replace with actual App ID if necessary
    "arn:aws:iam::370296042006:policy/RekognitionSetupCollection0RekognitionCollectionCustomResourcePolicyC35EF824"
)

# Loop through each resource and delete it
for resource in "${resources[@]}"; do
    echo "Deleting resource: $resource"

    # Check the type of resource and execute the appropriate delete command
    if [[ $resource == *"policy"* ]]; then
        # Delete IAM Policy
        aws iam delete-policy --policy-arn "$resource"
    elif [[ $resource == *"role"* ]]; then
        # Delete IAM Role
        aws iam delete-role --role-name "${resource##*:role/}"
    elif [[ $resource == *"apps"* ]]; then
        # Delete Amplify App (substituting ARN with App ID if necessary)
        app_id="${resource##*:apps/}"
        aws amplify delete-app --app-id "$app_id" --region "$REGION"
    else
        echo "Unsupported resource type for deletion: $resource"
    fi

    if [ $? -eq 0 ]; then
        echo "Successfully deleted resource: $resource"
    else
        echo "Failed to delete resource: $resource"
    fi
done