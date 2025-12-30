# Publish Image Skill

Upload images to public hosting services and get shareable links.

## Features
- Automatic upload to multiple services with fallback
- No API keys required
- Supports all common image formats (PNG, JPG, JPEG, GIF, WEBP, SVG)
- File size validation
- Direct URL response

## Usage

### From Synthia
Simply ask Synthia to publish an image:
- "Upload this image and give me a link"
- "Publish /tmp/diagram.png online"
- "Host this chart.jpg and share the URL"

### Manual Usage
```bash
cd /app/claude_home/.claude/skills/publish-image
./upload.sh /path/to/your/image.png
```

## Services Used

1. **0x0.st** (Primary)
   - Simple, reliable
   - 365-day retention
   - No registration needed

2. **catbox.moe** (Fallback)
   - Permanent hosting
   - No registration needed
   - Alternative if primary fails

## Limitations
- Maximum file size: ~100MB (varies by service)
- 0x0.st files expire after 365 days
- No authentication or private uploads

## Examples

```bash
# Upload a PNG
./upload.sh /tmp/architecture.png
# Returns: https://0x0.st/XXXX.png

# Upload a JPEG
./upload.sh ~/Downloads/photo.jpg
# Returns: https://0x0.st/YYYY.jpg
```

## Error Handling
The script will:
- Validate file exists before uploading
- Check file size and warn if large
- Try multiple services automatically
- Return clear error messages if all fail

## Output
The script outputs only the URL on success, making it easy to use in scripts:
```bash
URL=$(./upload.sh image.png)
echo "Image available at: $URL"
```
