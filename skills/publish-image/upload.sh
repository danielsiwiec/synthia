#!/bin/bash
# Image upload script for publish-image skill
# Usage: ./upload.sh /path/to/image.png

set -e

IMAGE_PATH="$1"

if [ -z "$IMAGE_PATH" ]; then
    echo "Error: No image path provided"
    echo "Usage: $0 /path/to/image.png"
    exit 1
fi

if [ ! -f "$IMAGE_PATH" ]; then
    echo "Error: File not found: $IMAGE_PATH"
    exit 1
fi

# Get file size in MB
FILE_SIZE=$(du -m "$IMAGE_PATH" | cut -f1)
if [ "$FILE_SIZE" -gt 100 ]; then
    echo "Warning: File is ${FILE_SIZE}MB, may exceed service limits"
fi

# Try 0x0.st first (365 day retention, simple)
echo "Uploading to 0x0.st..."
URL=$(curl -s -F "file=@$IMAGE_PATH" https://0x0.st)

if [ -n "$URL" ] && [[ "$URL" == https://* ]]; then
    echo "$URL"
    exit 0
fi

# Fallback to catbox.moe
echo "Trying catbox.moe..." >&2
URL=$(curl -s -F "reqtype=fileupload" -F "fileToUpload=@$IMAGE_PATH" https://catbox.moe/user/api.php)

if [ -n "$URL" ] && [[ "$URL" == https://* ]]; then
    echo "$URL"
    exit 0
fi

echo "Error: Upload failed on all services"
exit 1
