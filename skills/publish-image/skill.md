# Publish Image Skill

## Description
Upload an image file to a public hosting service and return a shareable link.

## Usage
Use this skill when the user asks to:
- Upload an image
- Publish an image online
- Get a shareable link for an image
- Host an image publicly

## Supported Services
This skill uses multiple image hosting services with fallback:
1. **0x0.st** - Simple, no API key required (365 day retention)
2. **imgbb.com** - Reliable backup option
3. **catbox.moe** - Alternative service

## Instructions

1. **Verify the image file exists**
   - Check that the file path is valid
   - Verify it's an image file (png, jpg, jpeg, gif, webp, svg)

2. **Upload to 0x0.st (primary)**
   ```bash
   curl -F "file=@/path/to/image.png" https://0x0.st
   ```
   - This returns a direct URL (e.g., https://0x0.st/XXXX.png)
   - Files are kept for 365 days
   - No API key required

3. **Fallback to catbox.moe if 0x0.st fails**
   ```bash
   curl -F "reqtype=fileupload" -F "fileToUpload=@/path/to/image.png" https://catbox.moe/user/api.php
   ```
   - Returns a direct URL (e.g., https://files.catbox.moe/xxxxx.png)
   - Permanent hosting
   - No API key required

4. **Return the result**
   - Provide the direct URL to the user
   - Verify the URL is accessible by checking the response
   - Format: `https://0x0.st/XXXX.png` or `https://files.catbox.moe/xxxxx.png`

## Error Handling
- If file doesn't exist: Report error and ask for correct path
- If upload fails on primary: Try fallback services
- If all services fail: Report error and suggest manual upload
- If file is too large (>100MB): Report size limitation

## Example Usage

### User asks: "Upload this diagram and give me a link"
1. Identify the image file path
2. Upload using curl to 0x0.st
3. Return: "Image uploaded: https://0x0.st/XXXX.png"

### User asks: "Publish /tmp/chart.png online"
1. Verify /tmp/chart.png exists
2. Upload to hosting service
3. Return direct link

## Notes
- Always use the `-F` flag with curl for file uploads
- Check response is a valid URL before returning
- Files on 0x0.st expire after 365 days
- Maximum file size is typically 100-500MB depending on service
- No authentication or API keys required for these services
