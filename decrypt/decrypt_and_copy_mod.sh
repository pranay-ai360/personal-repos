#!/bin/bash

# Base directory for decrypted files
destination_base="./decrypted"

# Import the GPG key
gpg --import keyring_all.asc

# Function to decrypt and copy while maintaining directory structure
process_files() {
  local src=$1
  local relative_path="${src#./}"  # Strip leading './' if present
  local dir_path=$(dirname "$relative_path")  # Get directory path relative to current directory
  local base_filename=$(basename "$relative_path")  # Get the base filename with extension

  # Modify to add "_decrypted" before the extension
  local output_filename="${base_filename%.*}_decrypted.${base_filename##*.}"

  # Path to place the decrypted file temporarily
  local full_output_path="./$dir_path/$output_filename"

  # Decrypt the file with gpg using a passphrase file
  gpg --no-use-agent --passphrase-file "passphrase.txt" --batch --output "$full_output_path" --decrypt "$src"

  echo "Decrypted: $src -> $full_output_path"

  # Full destination path
  local destination="$destination_base/$dir_path/$output_filename"

  # Ensure the destination directory exists
  mkdir -p "$(dirname "$destination")"

  # Move the decrypted file to its final destination
  mv "$full_output_path" "$destination"

  echo "Moved to: $destination"
}

# Export the function for use in 'find -exec'
export -f process_files

# Find all files in S3FOLDER and its subfolders, starting with 'UTR_' and process them
find ./S3FOLDER -type f -name 'UTR_*.csv' -exec bash -c 'process_files "$0"' {} \;