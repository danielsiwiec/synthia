---
description: Create a new Claude skill based on actions taken in the current session. Use when user asks to create a skill, save workflow as skill, or document a repeatable process.
---

## Overview
Creates a new skill in `/home/synthia/.claude/skills/` based on the history of actions taken in the current session. Skills capture repeatable workflows so they can be easily executed again.

## Skill Structure

Each skill lives in its own subfolder with a `SKILL.md` file:
```
/home/synthia/.claude/skills/
   my-skill-name/
      SKILL.md
```

## SKILL.md Format

### Frontmatter (Required)
```yaml
---
description: What it does and when to use it. Include trigger phrases. Max 1024 chars.
---
```

### Content Sections

1. **Overview** - Brief description of what the skill does
2. **API/Service Details** - Base URLs, credentials, endpoints (if applicable)
3. **Steps** - Numbered steps with code examples
4. **Known Values** - Common IDs, paths, or constants
5. **Troubleshooting** - Common issues and fixes
6. **Example Usage** - Phrases that should trigger this skill

## Steps to Create a Skill

1. **Identify the workflow** - Review the session history to find the repeatable actions
2. **Create the folder**:
   ```bash
   mkdir -p /home/synthia/.claude/skills/<skill-name>/
   ```
3. **Write SKILL.md** with:
   - Frontmatter with description (include trigger phrases)
   - Overview section
   - Step-by-step instructions with code examples
   - Troubleshooting section for common issues encountered
   - Example usage phrases
4. **Use lowercase-hyphenated naming** for the folder (e.g., `kavita-update-series-cover`)

## Code Examples Format

Use fenced code blocks with language specified:
```python
import urllib.request
# ... actual working code from the session
```

Include comments for important details like:
- Authentication requirements
- Required headers
- Expected responses
- Common pitfalls (e.g., "Just base64, no data URL prefix!")

## Troubleshooting Section

Document issues encountered during the session:
- What went wrong
- How it was diagnosed
- The fix that worked

## Example Skill Description

Good description:
```
Update a Kavita series cover to show the most recent issue/chapter. Use when user asks to update series cover, set cover to latest issue, or refresh magazine cover.
```

This includes:
- What it does
- When to use it (trigger phrases)

## Best Practices

- Keep skills focused on one task
- Include actual working code from the session
- Document API endpoints, credentials, and IDs
- Add troubleshooting based on real issues encountered
- Use clear step numbering
- Include example trigger phrases

## Example Usage
- "Create a skill for this workflow"
- "Save these steps as a skill"
- "Make a skill from what we just did"
- "Document this process as a reusable skill"
