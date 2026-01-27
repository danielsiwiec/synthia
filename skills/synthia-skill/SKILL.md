---
description: Create a new Claude skill based on actions taken in the current session. Use when user asks to create a skill, save workflow as skill, or document a repeatable process.
---

## Overview
Creates a new skill in `/home/synthia/.claude/skills/` based on the history of actions taken in the current session. Skills capture repeatable workflows so they can be easily executed again.

## Skill Types

There are two types of skills in Synthia:

### 1. Built-in Skills (Project-level)
**Location:** `/home/synthia/workdir/.claude/skills/`

These are core skills that come with the Synthia project. They are:
- Version-controlled with the project repository
- Shared across all users of the project
- Typically created by developers maintaining Synthia
- Examples: `synthia-skill`, `synthia-learn`, `publish-report`, `architecture-analyzer`

### 2. User-defined Skills (User-level)
**Location:** `/home/synthia/.claude/skills/`

These are custom skills created by users for their personal workflows. They are:
- Specific to the user's environment and needs
- Not version-controlled with the project
- Created dynamically based on user sessions and requests
- Examples: `sauna-controls`, `download-book`, `kavita-rescan`, `arr`, `shopping-research`

**When creating a new skill, always use the user-defined location** (`/home/synthia/.claude/skills/`) unless explicitly asked to create a built-in skill.

## Skill Structure

Each skill lives in its own subfolder with a `SKILL.md` file:
```
/home/synthia/.claude/skills/        # User-defined skills
   my-skill-name/
      SKILL.md

/home/synthia/workdir/.claude/skills/ # Built-in skills
   core-skill-name/
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
