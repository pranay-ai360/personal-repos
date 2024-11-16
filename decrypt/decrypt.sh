#!/bin/bash

# Loop through all directories and subdirectories
find . -type f -name 'UTR_SENDRECEIVE*.txt' | while read -r filename; do
  # Remove './' prefix and '.txt' suffix to construct the new filename
  base=${filename#./}
  base=${base%.txt}

  # Construct the output filename by appending .csv
  output_filename="${base}.csv"

  # Decrypt the file with gpg
  gpg --decrypt -o "$output_filename" "$filename"

  echo "Decrypted: $filename -> $output_filename"
done
