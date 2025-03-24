#!/bin/bash

# Export AWS credentials
export AWS_DEFAULT_REGION=ap-southeast-1
export AWS_ACCESS_KEY_ID="xx"
export AWS_SECRET_ACCESS_KEY="x+x"
export AWS_SESSION_TOKEN=""
# Define the S3 bucket base path
S3_PATH="s3://eit-vdatalake/raw/unstructured/reconart/Crypto/2025/"
LOCAL_DIR="./downloaded_files_2025"

# Create local directory if not exists
mkdir -p "$LOCAL_DIR"

# List and download files matching the pattern recursively
#aws s3 ls "$S3_PATH" --recursive | awk '{print $4}' | grep -E 'fireBlock_UTR_.*' | while read -r file; do
#aws s3 ls "$S3_PATH" --recursive | awk '{print $4}' | grep -E 'fireBlock_*' | while read -r file; do
aws s3 ls "$S3_PATH" --recursive | awk '{print $4}' | grep -E 'UTR_*' | while read -r file; do
    echo "Downloading $file..."
    aws s3 cp "s3://eit-vdatalake/$file" "$LOCAL_DIR/$(basename "$file")"
done

echo "Download complete."
