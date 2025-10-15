# Agent Learnings: magazines

## Browser Token Limit Handling
- When browser snapshots exceed token limits (>25000 tokens), the browser will return an error message instead of completing the action
- Direct URL navigation using `browser_navigate` bypasses oversized page snapshots that cause token limit errors
- For download pages on freemagazines.top, navigate directly to the article URL (e.g., `https://freemagazines.top/tabletop-gaming-issue-106-september-2025`) instead of clicking search result links
- When clicking download links also triggers token limit errors, navigate directly to the download service URL (e.g., LimeWire link) instead

## LimeWire Download Process
- LimeWire is used as the download service for freemagazines.top
- After navigating to a LimeWire download URL, wait 3 seconds for the page to load completely before interacting
- The download button becomes active immediately and can be clicked
- Downloads progress in the background - wait approximately 30-60 seconds for files to complete (monitor download progress percentage in snapshots)
- Downloaded files are saved to `/Users/dansiwiec/daimos/.playwright-mcp/` with URL-formatted filenames (spaces replaced with hyphens)
- Move downloaded files from the `.playwright-mcp` folder to the target magazine directory with proper naming format

## File Naming Convention
- Follow the format: `[Magazine Name] - Issue [Number], [Month] [Year].pdf`
- Example: `Tabletop Gaming - Issue 106, September 2025.pdf`
- This differs from the download filename which uses a compressed format

## Monthly Publication Expectations
- Tabletop Gaming is a monthly publication
- An issue from the previous month (e.g., September issue in mid-October) is still current and should be downloaded
- Only skip downloads if the issue is more than a month old, as specified in the agent instructions

## Browser Session Management
- Always close the browser using `browser_close` after completing downloads to avoid leaving sessions open
- Multiple tabs may open during navigation (especially with LimeWire) - closing via `browser_close` handles all tabs

## The Economist Specifics
- The Economist USA releases weekly issues (not monthly)
- Issues are dated with specific publication dates (e.g., "Oct 11, 2025") rather than just month/year
- The current issue is typically the most recent weekly date, with next issue expected approximately 7 days later
- File sizes for The Economist are typically 35-45 MB
- When checking if current: compare the issue date with today's date and account for the weekly publication schedule
- An issue that is 3-7 days old is still current; do not attempt to download if the latest available issue on the website matches what's already in the folder