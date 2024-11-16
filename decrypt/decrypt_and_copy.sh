#!/bin/bash

# Base directory for decrypted files
destination_base="./decrypted"

# Import the GPG key
gpg --import keyring_all.asc

# Function to decrypt and copy maintaining directory structure
process_files() {
  local src=$1
  local relative_path="${src#./}"  # Strip leading './' if present
  local dir_path=$(dirname "$relative_path")  # Get directory path relative to current directory
  local base_filename=$(basename "$relative_path" .txt)  # Get the base filename without extension

  local output_filename="$base_filename.csv"  # Name of the decrypted file
  local full_output_path="./$dir_path/$output_filename"  # Path to place the decrypted file temporarily

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

# Find all files and process them
find . -type f -name 'UTR_SENDRECEIVE*.txt' -exec bash -c 'process_files "$0"' {} \;
