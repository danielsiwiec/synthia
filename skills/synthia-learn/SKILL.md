---
description: Learn from the current session - improve existing synthia skills and extract valuable facts to remember. Use when user asks to learn from this session, improve a skill, update skill with lessons learned, refine skill from experience, remember this, save this for later, or extract facts.
---

## Overview

Analyzes the current session to:
1. Identify improvements for existing synthia skills
2. Extract valuable facts and information worth remembering for future conversations

This skill extracts lessons learned, edge cases discovered, better approaches found, troubleshooting insights, and personal/contextual facts from the session history.

## When to Use

- After completing a task using an existing skill that had issues or workarounds
- When a better approach was discovered during execution
- When new edge cases or troubleshooting steps were found
- When the user explicitly asks to improve a skill based on session experience
- When the user shares personal information, preferences, or context worth remembering
- When important facts, configurations, or decisions are discussed
- When the user says "remember this" or "save this for later"

## Steps

1. **Identify the skill(s) used in this session**
   - Review the session history for Skill tool invocations
   - Note which skill(s) were triggered and used

2. **Analyze what happened**
   - What was the original task?
   - Did the skill instructions lead to success on the first try?
   - Were there any errors, retries, or workarounds needed?
   - Was a better approach discovered?
   - Were there missing steps or unclear instructions?

3. **Extract improvements**
   - New troubleshooting entries for errors encountered
   - Additional steps that were needed but not documented
   - Better code examples that worked more reliably
   - New known values (IDs, paths, constants) discovered
   - Clearer explanations for confusing parts
   - Edge cases that should be handled

4. **Read the existing skill file**
   ```bash
   cat /app/claude_home/.claude/skills/<skill-name>/SKILL.md
   ```

5. **Update the skill with improvements**
   - Add new troubleshooting entries
   - Refine or add steps
   - Update code examples with working versions
   - Add newly discovered known values
   - Clarify instructions that were confusing
   - Update the description if trigger phrases should change

6. **Preserve skill structure**
   - Keep the frontmatter with description
   - Maintain existing sections that still apply
   - Add new sections if needed (e.g., Troubleshooting if missing)

## Part 2: Extracting Valuable Facts

### Steps for Fact Extraction

1. **Analyze the conversation for valuable facts**
   - Personal information (names, roles, preferences, schedules)
   - Technical context (project names, technologies used, architecture decisions)
   - Preferences and habits (coding style, communication preferences)
   - Important dates, deadlines, or recurring events
   - Credentials, API endpoints, or configuration values (non-sensitive)
   - Relationships and team structures
   - Goals, plans, and ongoing projects

2. **Evaluate fact quality**
   - Is this likely to be useful in future conversations?
   - Is this stable information (not temporary state)?
   - Is this specific enough to be actionable?
   - Avoid storing: temporary states, one-time tasks, sensitive credentials

3. **Save facts using the memory MCP**
   - Use the `add-memory` tool from the memory MCP server
   - Each fact should be stored as a separate memory entry
   - The content should be a clear, concise statement of the fact

### Using the Memory MCP

Use the `add-memory` tool to store each fact:

```
Tool: add-memory
Parameters:
  - content: "User's name is Dan and works on the synthia project"
```

For multiple facts, call `add-memory` once per fact:
- "User prefers concise responses without emojis"
- "Project uses Python with uv for package management"
- "Discord is used for notifications"

### What Makes a Good Fact

**Good facts:**
- "User prefers dark mode in all applications"
- "The production server is at api.example.com"
- "Team standup is every day at 9am"
- "Project uses PostgreSQL for the main database"

**Bad facts (don't store):**
- "User asked about the weather today" (temporary)
- "Current task is fixing a bug" (transient state)
- "API key is abc123" (sensitive credential)

## What to Improve

### Troubleshooting Section
Add entries for any errors encountered:
```markdown
## Troubleshooting

### Error: <error message or symptom>
**Cause**: Why this happened
**Fix**: What solved it
```

### Steps Section
- Add missing steps that were needed
- Reorder steps if the original order caused issues
- Add warnings or notes before tricky steps

### Code Examples
- Replace code that didn't work with code that did
- Add comments explaining non-obvious parts
- Include actual working values from the session

### Known Values
- Add any new IDs, paths, or constants discovered
- Document where values came from

## Best Practices

- Only update skills that were actually used in the session
- Be specific about what was learned (include error messages, actual values)
- Don't remove existing content unless it's wrong
- Add context for why changes were made (e.g., "Added after discovering X")
- Keep improvements focused on real issues encountered, not hypotheticals

## Example Improvements

**Before (missing troubleshooting):**
```markdown
## Steps
1. Call the API endpoint
```

**After (with lesson learned):**
```markdown
## Steps
1. Call the API endpoint
   - Note: Returns 401 if token expired; refresh token first if call fails

## Troubleshooting

### 401 Unauthorized on API call
**Cause**: Auth token expired
**Fix**: Call the refresh endpoint first, then retry
```

## Example Usage

### For Skill Improvement
- "Learn from this session and improve the skill"
- "Update the skill with what we learned"
- "Save these lessons to the skill"
- "Improve the skill based on what just happened"
- "Refine the skill from this experience"

### For Fact Extraction
- "Remember this for later"
- "Save this information"
- "Learn from this conversation"
- "Extract any useful facts from our chat"
- "What should you remember from this session?"

### Combined
- "Learn everything from this session" (improves skills AND extracts facts)
- "Save what you've learned" (both skill improvements and facts)
