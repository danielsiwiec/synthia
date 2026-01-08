---
description: Publish a PDF report from a given content
---

## Overall guidance
- Use the `publish.py` script in this skill directory to publish content to MarkdownPaste
- Run: `echo "content" | python publish.py "title"`
- The script will return the document link in the format: https://www.markdownpaste.com/document/[slug]
- Ensure the link works and shows the published content by navigating to it with a browser
- Respond with the document link

## Image handling
- **NEVER use placeholder or guessed image URLs** - they will not load in the published report
- **ALWAYS use actual image URLs** extracted from the source pages you visited during research
- To get real image URLs:
  1. Navigate to the source page containing the image
  2. Use `browser_evaluate` to extract the actual `src` attribute: `() => document.querySelector('img[alt*="keyword"]').src`
  3. Use CDN-hosted URLs (e.g., `m.media-amazon.com`, `i.imgur.com`, `cdn.example.com`)
- **Avoid** manufacturer marketing URLs (e.g., `bmwusa.com/content/dam/...`) - these often block external embedding
- If you cannot obtain a real image URL, omit the image rather than using a broken placeholder
- Test that images load by checking the published report in the browser before returning the link

### Image Syntax - IMPORTANT
- **DO NOT use standard markdown image syntax** like `![alt](url)` - MarkdownPaste does not render this correctly (the `!` appears as text and the rest becomes a broken link)
- **USE HTML img tags instead**:
  ```html
  <img src="https://example.com/image.jpg" alt="Description" width="200">
  ```
- Example for Amazon product images:
  ```html
  <img src="https://m.media-amazon.com/images/I/71O7g5Ts7iL._AC_SX679_.jpg" alt="Product Name" width="200">
  ```