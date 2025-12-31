---
description: Analyze Synthia's codebase architecture and generate comprehensive documentation. Use when user asks to analyze architecture, document codebase structure, or understand Synthia's design. (project)
---

## Overview

Performs high-level analysis of the Synthia codebase and generates architectural documentation in `/home/synthia/.claude/data/synthia_architecture.md`. This skill focuses on system design, component relationships, and agent capabilities rather than implementation details.

## Guiding Principles

1. **High-Level Focus** - Document what components do, not how they're implemented
2. **No Code Snippets** - Use prose descriptions and diagrams instead of copying code
3. **Conceptual Clarity** - Explain purpose and relationships, not internal mechanics
4. **Verify Numbers** - Line counts, port numbers, and counts must come from actual commands
5. **Agent-Centric** - Emphasize AI agent architecture and capabilities

## Steps

### 1. Gather Project Metrics

Collect basic quantitative data:

```bash
# Count Python files
find /home/synthia/synthia -name "*.py" | wc -l

# Count lines of code (approximate)
find /home/synthia/synthia -name "*.py" -exec cat {} \; | grep -v '^\s*#' | grep -v '^\s*$' | wc -l

# Count skills
ls /home/synthia/claude_home/.claude/skills/ | wc -l
```

### 2. Read Core Configuration

Read these files to understand system setup:
- `/home/synthia/docker-compose.yml` - Services, ports, volumes
- `/home/synthia//pyproject.toml` - Dependencies (names only, not versions)
- `/home/synthia/synthia/main.py` - Entry point and configuration

Extract key facts:
- Port mappings
- Service dependencies
- Environment variables
- Key dependency categories

### 3. Identify Core Components

Scan the codebase structure:

```bash
# List main modules
ls -la /home/synthia/synthia

# List agent-related modules
ls -la /home/synthia/synthia/agents/
```

For each major component, understand its **purpose** (not implementation):
- What problem does it solve?
- What other components does it interact with?
- What is its public interface?

### 4. Analyze Agent Architecture (NEW - CRITICAL SECTION)

This section focuses specifically on the AI agent capabilities. Document:

**Agent Core:**
- What SDK/framework powers the agent (Claude Agent SDK)
- How the agent is configured (system prompt themes, permissions, working directory)
- Session management capabilities (new vs resume)

**Tool Ecosystem:**
- List all MCP servers and their tool categories
- Describe what each tool category enables (memory, scheduling, browser automation)
- Note any external tool servers

**Skills System:**
- How skills extend agent capabilities
- Skill discovery mechanism
- List available skills with one-line descriptions

**Agent Event Flow:**
- How agent messages are processed
- What events are published during execution
- How progress is tracked and reported

**Agent Limitations & Boundaries:**
- Permission model
- What the agent can/cannot do autonomously

### 5. Map System Architecture

Create a high-level architecture diagram showing:
- Client entry points (API, Discord)
- Core services and their relationships
- Data stores
- External integrations

Use ASCII art diagrams - keep them conceptual, not detailed.

### 6. Document Data Flow

Describe the request lifecycle at a high level:
1. Request entry points
2. Orchestration layer
3. Agent execution
4. Event publishing
5. Response delivery

Include a simple flow diagram.

### 7. Document Extension Points

List how the system can be extended:
- Adding skills (brief process)
- Adding MCP servers (brief process)
- Adding event handlers
- Adding API endpoints

Keep descriptions to 2-3 lines each.

### 8. Generate Documentation

Delete existing documentation first:
```bash
rm -f /home/synthia/.claude/data/synthia_architecture.md
mkdir -p /home/synthia/.claude/data/
```

Create documentation with these sections:

1. **Overview** - What Synthia is, key metrics table, core capabilities list
2. **System Architecture** - ASCII diagram showing component relationships
3. **Component Overview** - Brief description of each major component (2-4 sentences each)
4. **Agent Architecture** - Dedicated section on AI agent capabilities:
   - Agent core (SDK, configuration, sessions)
   - Agentic capabilities (RAG, memory system, background agents, self-learning)
   - Tool ecosystem (MCP servers and their purposes)
   - Skills system (how it works, available skills table)
   - Event flow (how agent activity is tracked)
5. **Meta capabilities** - Synthia's ability to work on itself
6. **Data Flow** - Request lifecycle diagram
7. **Storage** - What is persisted and where
8. **Configuration** - Environment variables table, key dependencies table
9. **Extension Points** - How to extend each component (brief)
10. **Synthia vs Claude Code** - Comparison table showing unique capabilities Synthia provides beyond vanilla Claude Code
11. **Deployment** - Services and startup commands

### 9. Document Synthia vs Claude Code

Create a dedicated section comparing Synthia to pure Claude Code. This section should highlight capabilities that Synthia has that vanilla Claude Code does not provide out of the box. Review all of Synthia's agentic capabilities and highlight the differences from Claude Code. Include things like learning, memories, meta-capbilities, etc.

**How to Present:**
- Create a clear comparison table
- Use brief explanations (one sentence per capability)
- Focus on user-facing benefits, not implementation details
- Group related capabilities together

### 10. Verify Documentation

Quick verification checks:
- Port numbers match docker-compose.yml
- File/skill counts match actual counts
- All major directories are mentioned
- No code snippets included (except deployment commands)
- Synthia vs Claude Code section is accurate and complete

## Output Format Guidelines

**DO:**
- Use tables for lists of items (skills, env vars, dependencies)
- Use ASCII diagrams for architecture and flow
- Use bullet points for capabilities and features
- Keep component descriptions to 2-4 sentences
- Focus on "what" and "why", not "how"

**DON'T:**
- Include code snippets or class definitions
- Copy type annotations or function signatures
- Document internal implementation details
- Include field-level model documentation
- Show configuration file contents verbatim

## Example Section Formats

### Good - Component Description:
```
### Task Service

The orchestration layer between API/Discord and the Claude Agent. It validates
request schemas, manages session continuity for conversations, and can parse
unstructured agent responses into structured formats using an LLM.
```

### Bad - Too Much Detail:
```
### Task Service

```python
class TaskService:
    def __init__(self, claude_agent: ClaudeAgent):
        self._last_session_id: str | None = None
...
```

### Good - Skills Table:
```
| Skill | Purpose |
|-------|---------|
| `magazines` | Download and check for new magazine issues |
| `arr` | Manage arr services (Sonarr, Radarr, etc.) |
```

### Bad - Skills Detail:
```
The magazines skill is located at /home/synthia/.claude/skills/magazines/SKILL.md
and contains the following sections: Overview, Modes (Mode 1: Check for new issues,
Mode 2: Download specific magazines), Error handling...
```

## Known Paths

- Main app: `/home/synthia/`
- Built-in skills: `/home/synthia/workdir/.claude/skills/`
- User-defined skills: `/home/synthia/.claude/skills/`
- Documentation output: `/home/synthia/.claude/data/synthia_architecture.md`
- Config files: `/home/synthia/pyproject.toml`, `/home/synthia/docker-compose.yml`

## Example Usage

- "Analyze Synthia's architecture"
- "Document the codebase structure"
- "Generate architecture documentation"
- "Explain Synthia's design"
- "What is Synthia's agent architecture?"

## Response to User

After completing the analysis and generating the documentation, respond to the user with exactly:

"Architecture analysis complete."

Do not include any other text, summaries, or explanations in your response.
