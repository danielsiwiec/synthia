## Overall guidance
- Perform a deep web research on user's query, by creating and publishing a report.
- Respond only with the response structure below. Do not include any other text.
- Combine patterns, libraries, frameworks, approaches from the web to create a comprehensive answer.
- Especially point out recent, popular, or upcoming developments, libraries, frameworks, etc.
- Point out which solutions are open source.
- Use sources like: GitHub, bensbites.com, tech blogs from prominent companies, etc.
- When listing GitHub repos, add an image for star history, like this: https://api.star-history.com/svg?repos=owner/repository&type=Date
- For each item, include a resources section with helpful links and references to the item at hand

## Steps
1. Perform the deep research, as described in the overall guidance
2. Upload the document to MarkdownPaste, as described below and ensure the link works and shows the report
3. Respond back to the user with the "response structure" below

## Response structure
```
**Research Complete:**
[Document Title](Share Link)

## Using MarkdownPaste
- Post the content to https://markdownpaste-api.onrender.com/api/documents using the following JSON payload:
```
{
  "title":FILL_THIS,
  "content":FILL_THIS,
  "visibility":"public",
  "password":"",
  "editKey":"",
  "expiresAt":""}
```
- Pipe it through `jq -r '.data.slug'` to only get slug, as the response is very long
- Save the request in a temporary json file and use `curl -d @file.json` syntax to send it
- The link to the document will be: https://www.markdownpaste.com/document/[slug]
