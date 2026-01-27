---
description: Generate promotional marketing content for Synthia targeting general audiences (non-technical to barely technical). Focus on real-world benefits, relatable use cases, and emotional outcomes. Use when user asks to create marketing materials or promotional content. (project)
---

## Overview

Generates compelling promotional content in `/home/synthia/.claude/data/synthia_product.md` for general audiences. This is benefit-focused marketing that speaks to busy professionals, small business owners, and individuals seeking practical AI assistance - not technical documentation.

**Critical:** Keep it brief (~100 lines total). Every sentence must earn its place. Scannable, punchy, quick to read.

## Guiding Principles (2026 Best Practices)

1. **Brevity First** - Target ~100 lines total. Every sentence must earn its place
2. **Outcomes Over Features** - Show how Synthia improves daily life, saves time, reduces stress
3. **Plain Language** - Zero technical jargon; explain everything like talking to a friend
4. **Punchy and Scannable** - Short paragraphs (2-3 sentences max), bold headers, quick reads
5. **Emotional Connection** - Address frustrations, aspirations, and practical needs
6. **Conversational Tone** - Write like you're helping a friend, use "you" language
7. **Analogies and Metaphors** - Translate technical concepts into familiar experiences

## Steps

### 1. Understand Current Capabilities

Review the architecture documentation to understand what Synthia offers:
- Read `claude_home/data/synthia_architecture.md` - focus on "Core Capabilities" and "Extension Points"
- Note MCP servers and what they enable
- Identify 5-7 extra capabilities to highlight

**Critical:** Translate EVERY technical capability into a relatable life benefit:

**Emphasize these core areas:**
- "Persistent memory" → "Remembers every conversation forever" (CORE)
- "Self-learning/skill refinement" → "Show it once, it learns forever. Teach Synthia your way of working." (CORE - EMPHASIZE TEACHING!)
- "Task scheduling/reminders" → "Set reminders once, get automated summaries, runs while you sleep" (CORE - emphasize reminders!)
- "Image generation" → "Want an image? Just describe it" (CORE)
- "Multi-channel access" → "Everything happens through conversation - just talk" (CORE)
- "Extensibility" → "Connects to your tools - Calendar, Gmail, web forms" (CORE)

**Supporting capabilities:**
- "Episodic memory" → "Search past conversations - pull up discussions from months ago"
- "Browser automation" → "Handles repetitive web tasks for you"

### 2. Identify Key Differentiators

Translate technical features into everyday benefits using analogies:

**vs ChatGPT (explain like talking to a neighbor):**
- Memory: Like having a friend who remembers everything you've ever told them vs meeting a stranger each time
- Teaching: You can teach it your way of working vs starting from scratch every time
- Reminders & automation: Set it once and forget it vs having to remember everything yourself
- Multi-channel: Text from anywhere - phone, computer, voice - conversation continues seamlessly
- Privacy option: Keep your conversations private on your own devices (like a diary vs public journal)

**vs Claude Code (for barely technical users):**
- Memory: Never explain your preferences twice - Synthia remembers permanently
- Background work: Set it once, it runs automatically (like a programmable thermostat)
- Access anywhere: Start conversation on computer, continue on phone, finish with voice
- Learning: Remembers successful solutions and suggests them for similar problems
- Always available: Works 24/7, even when you're offline

### 3. Define Target Audiences

Identify who would benefit most (non-technical focus):
- Busy professionals juggling multiple projects
- Small business owners managing day-to-day operations
- Remote workers coordinating across time zones
- Parents organizing family schedules and tasks
- Students managing coursework and research
- Entrepreneurs building their business
- Anyone frustrated with forgetting important details
- People seeking work-life balance through automation

### 4. Create Use Case Examples

Develop 5-7 relatable, everyday scenarios that non-technical users can picture:
- "Teach Synthia how you like your reports formatted - it learns and does it your way forever"
- "'Here's my client onboarding process' - show it once, Synthia runs it every time"
- "Get a Sunday evening summary of everything you need to know for the week ahead"
- "'Remind me to water plants every Thursday' - set once, it happens automatically"
- "Ask 'What did Sarah say about the budget in March?' - Synthia remembers"
- "Every Monday morning, get a summary of what's coming up - you didn't even have to ask"
- "'Don't let me forget Mom's birthday' - Synthia reminds you in advance, every year"
- "Show Synthia your morning routine once - it helps you stick to it automatically"

### 5. Generate Marketing Content

Delete existing content first:
```bash
rm -f /home/synthia/.claude/data/synthia_product.md
mkdir -p /home/synthia/.claude/data/
```

Create promotional page with these sections (KEEP IT BRIEF - ~100 lines total):

1. **Title & Subtitle**:
   - Title: Punchy, benefit-focused (e.g., "Your AI Assistant That Actually Works")
   - Subtitle: Bold, single line - remembers, learns, runs continuously
2. **Hero Section** (2-3 sentences) - Relatable everyday scenario showing instant recall, ending with: "Teach it once, it knows forever"
3. **The Problem** (3-4 sentences) - Core frustrations including "can't teach it how you work"
4. **The Solution** (4 subsections, 2-3 sentences each):
   - **It Actually Remembers** - Persistent memory for conversations and facts
   - **Teach It How You Work** - Show it once, it learns forever. Use "teach", "show", "learn" language (EMPHASIZE THIS!)
   - **It Works While You Sleep** - Reminders, automated summaries, scheduled tasks (EMPHASIZE REMINDERS!)
   - **Just Talk to It** - Everything conversational: images, calendar, web tasks, multi-channel
   - Add transition: "Here's how this plays out in real life:"
5. **Real Stories** (3 condensed scenarios) - Bold title + single paragraph format
   - Include at least one teaching/learning example
6. **Who This Helps** (4 personas, 2 sentences each) - Use "teach" language: "Teach Synthia X", "Show Synthia Y"
7. **Comparison Table** (5 rows max) - Plain language, must include "Learn how you work" and "Get reminders" rows
8. **Getting Started** (3 steps, single-line format):
   - Step 1: Just start talking - "Synthia listens and learns"
   - Step 2: Show It How You Work - "Teach Synthia by example" (EMPHASIZE!)
   - Step 3: Set reminders once - happens automatically
9. **Social Proof** (3 quotes) - Include at least one teaching-focused quote ("I taught it X")
10. **CTA** (2-3 sentences) - Must include actionable link/instruction with clear next step

### 6. Write for Real People

For each capability, use the "So What?" test:
- How does this make someone's day easier?
- What stress does it remove?
- What time does it save?
- How does it make them feel?

**Use analogies to explain complex ideas:**
- Memory = "Like having a journal that writes itself and you can search instantly"
- Automation = "Like a helpful roommate who does chores while you sleep"
- Multi-channel = "Start a conversation in the kitchen, continue it in the car"

**Good example (emotional + practical):**
"Stop repeating yourself. Imagine having a conversation partner who remembers everything - your food preferences, your project deadlines, what your boss said three months ago. That's Synthia. It's like finally having someone who listens and never forgets."

**Bad example (technical):**
"Synthia uses pgvector to store semantic embeddings of conversational memory in PostgreSQL."

**Good example (relatable scenario):**
"It's Sunday night. Instead of scrambling through emails and notes trying to remember what's due this week, just ask Synthia. It already knows your schedule, your priorities, and what's coming up. Get back to relaxing."

**Bad example (feature list):**
"Synthia supports task scheduling with cron-based job execution and calendar integration."

### 7. Create Comparison Tables (Plain Language)

Build clear comparison tables using everyday language:

**Format (focus on daily life impact):**
| What You Want | ChatGPT | Synthia |
|---------------|---------|---------|
| Remember past conversations | Forgets when you close the tab | Remembers forever - ask about anything, anytime |
| Work while you're busy | You have to ask every time | Sets up once, runs automatically |
| Access from anywhere | Web browser only | Phone, computer, voice - your choice |

**Rules for comparisons:**
- Use "what you want" or "when you need" language, not feature names
- Describe the experience, not the technology
- Focus on time saved, stress reduced, problems solved
- Use relatable scenarios: "Remember what your colleague said last month"

### 8. Add Storytelling Elements (Condensed Format)

Use **condensed story format** for maximum impact with minimum words:

**Format: Bold Title + Single Paragraph**
```
**Sunday Evening Peace:** Instead of spending an hour scrolling through emails, you ask Synthia. Two minutes later, you have everything - deadlines, meetings, that thing your boss mentioned Friday. You're prepared.
```

**Before/After Transformations (Tight):**
"Every time you open ChatGPT, it's like talking to a stranger. With Synthia, tell it once - it remembers forever."

**Keep Stories to 3 Maximum:**
- Pick the most relatable moments only
- Each story: 2-3 sentences max
- Bold title, immediate scenario, clear benefit

**Sensory Language (Brief):**
"Imagine waking up to..." "Picture yourself..." - Use sparingly, keep punchy

### 9. Verify Content (General Audience Test)

**Brevity Check (CRITICAL):**
- Total length: ~100 lines or less?
- Any paragraph longer than 2-3 sentences? Condense it
- Any section over 10 lines? Tighten it
- More than 3 stories? Cut to best 3
- More than 4 personas? Cut to 4
- More than 3 quotes? Cut to 3

**The "Mom Test":** Would your non-technical friend/parent understand this?
- Could someone with zero tech background understand every sentence?
- Are analogies relatable to everyday life?
- Is every technical term either removed or explained in plain language?
- Does each section answer "What's in it for me?" immediately?
- Can readers picture themselves using this?
- Is the tone conversational, not corporate?
- Does the comparison table use everyday language?

**Scannable Check:**
- Can someone skim the whole page in 3-5 minutes?
- Are headers clear and benefit-focused?
- Is it punchy and easy to digest?

## Output Format Guidelines

**DO:**
- **Keep it brief** - Target ~100 lines total, every sentence earns its place
- Lead with emotional outcomes: "Feel organized," "Save hours," "Never forget"
- Use everyday analogies: "Like having a personal assistant who never sleeps"
- Write like talking to a friend over coffee
- Use condensed story format: **Bold Title:** Single paragraph
- Keep paragraphs to 2-3 sentences maximum
- Make it scannable - bold headers, short sections, quick reads
- Use active, conversational tone
- Show before/after transformations (briefly)
- Consolidate extra capabilities into brief "Plus:" lines within main sections
- Add transitions between major sections to maintain flow
- Include actionable CTAs with actual links or clear next steps

**DON'T:**
- Write long sections - if a section is >10 lines, condense it
- Use ANY technical terms without translating them first
- Assume readers know what "API," "scheduling," "automation" mean
- List features without explaining the life benefit
- Write in corporate/formal tone
- Use developer or IT jargon
- Make it sound complicated or intimidating
- Write paragraphs longer than 2-3 sentences
- Include more than 3 stories, 4 personas, 3 quotes
- Create separate sections for every capability - consolidate instead
- End with vague CTAs like "Start today" without actionable links

## Example Content Formats

### Good - Punchy Title & Subtitle:
```
# Your AI Assistant That Actually Works

**Perfect memory. Smarter every day. Runs 24/7.**
```

### Good - Alternative Titles:
```
# AI Assistant That Finally Doesn't Suck
# Your AI That Never Forgets
# The AI Assistant You've Been Waiting For
```

### Bad - Generic Title:
```
# Synthia - Advanced AI Platform
# Meet Synthia
```

### Good - Hero Section (Everyday Life Scenario):
```
**Perfect memory. Smarter every day. Runs 24/7.**

"How do I make that pasta dish Mom loved?" You ask Synthia. Instantly: the recipe you described six months ago, the exact measurements, that weird ingredient you found at the farmer's market. You'd completely forgotten you told it.

That's Synthia. Teach it once, it knows forever.
```

### Good - Alternative Hero Examples:
```
Your phone buzzes: "Your mom's birthday is in 3 days. You usually order from that bakery on Main Street." You told Synthia about this once, a year ago. It remembered. You didn't.

That's Synthia. Teach it once, it knows forever.
```

### Good - Emotional Hook with Analogy:
```
### Your AI Assistant That Actually Remembers

You know that friend who remembers every detail of every conversation you've ever had?
The one who recalls that random restaurant you mentioned six months ago?
That's Synthia. Except it never sleeps, never forgets, and is always there when you need it.
```

### Bad - Technical Feature Description:
```
### Semantic Memory System

Synthia implements a semantic memory system using pgvector and mem0ai for persistent storage.
```

### Good - Learning/Teaching Section (IMPORTANT - ALWAYS INCLUDE):
```
### Teach It How You Work

Show Synthia once, it learns forever. "Here's how I like my weekly reports." "This is my meeting prep routine." "Here's how I organize my notes." Synthia learns your way of doing things and gets better at helping you specifically.

Next time you need it, Synthia already knows. No templates. No repeated instructions. Just "do that thing we did last time."
```

### Good - Teaching Story Example (Include at least one):
```
**Just Show It Once:** "Here's how I like my monthly reports formatted." You teach Synthia by example. Next month, it generates one perfectly. You tweak a detail. From then on, every report is exactly right. It learned your style.
```

### Good - Reminders/Scheduling Section (IMPORTANT - Emphasize reminders):
```
### It Works While You Sleep

Like a coffee maker that brews automatically, Synthia runs tasks on schedule. Tell it once: "Every Monday morning, summarize my week." Done. It happens automatically while you're sleeping.

"Remind me to water plants every Thursday." Set once, forget about it. Synthia handles it.
```

### Good - Condensed Story Format:
```
**Monday Morning Made Easy:** You told Synthia once: "Every Monday at 8am, tell me what's coming up." Now Monday mornings, coffee in hand, the summary is already there. You didn't have to remember to ask. It happened while you slept.
```

### Bad - Too Long/Technical:
```
**Monday Morning Made Easy**

It's 7 AM. You just sat down with your coffee. You're trying to remember what's on your schedule for the week. Instead of frantically scrolling through emails, calendar notifications, and notes trying to piece together what's due this week, you ask Synthia. It already compiled everything - deadlines, meetings, that thing your colleague mentioned on Friday. Two minutes and you're ready for the week. (TOO LONG - should be 2-3 sentences max)

**Task Scheduling**
Synthia supports APScheduler-based job scheduling with cron syntax. (TOO TECHNICAL)
```

### Good - Plain Language Comparison (Must include "Learn" and "Reminders" rows):
```
| What You Want | ChatGPT | Synthia |
|---------------|---------|---------|
| Remember past conversations | Forgets when you close the tab | Remembers forever |
| Learn how you work | Starts from zero each time | Gets better at helping you |
| Get reminders | You have to remember to ask | Set once, reminded automatically |
| Access anywhere | Web browser only | Phone, computer, voice |
```

### Bad - Technical Comparison:
```
| Feature | ChatGPT | Synthia |
|---------|---------|---------|
| Memory Architecture | Session-based context windows | PostgreSQL-backed persistent memory with pgvector |
```

### Good - Problem → Solution:
```
**The Problem:** You tell ChatGPT your preferences every single time. "I'm vegetarian."
"I prefer Python." "My deadline is Friday." Over and over.

**With Synthia:** Tell it once. It remembers. Forever. Like talking to someone who
actually listens.
```

### Good - Condensed Persona (use "teach" language):
```
**Busy Professionals:** Managing multiple projects, client preferences, deadlines. Teach Synthia your workflow once - it remembers and improves it every time you use it.
```

### Bad - Too Detailed Persona:
```
**Busy Professionals**

If you're a busy professional, you're likely managing multiple projects at once. You need to remember client preferences, track deadlines, coordinate with team members, and keep all the details straight. Your brain is full and you can't afford to forget important information. Synthia becomes your external memory, storing every client detail, every project note, every commitment permanently so you look more organized because you actually are more organized. (TOO LONG - should be 2 sentences max)
```

### Good - Conversational Interface Section (Emphasize everything via chat):
```
### Just Talk to It

Everything happens through conversation. Want an image? Describe it. Need to check your calendar? Ask. Fill out web forms? Tell Synthia once, it handles it forever.

Computer, phone, voice - wherever you are, just talk. Same conversation, same memory, like texting a friend who actually remembers.
```

### Good - Condensed Getting Started (Emphasize teaching):
```
**Just Start Talking:** Share what's on your mind - projects, preferences, things to remember. Synthia listens and learns.

**Show It How You Work:** "Here's how I format reports." "This is my client onboarding process." Teach Synthia by example - it learns your workflow and does it your way.

**Set Reminders Once:** "Every Sunday, summarize my week." "Remind me about Mom's birthday." Said once. Happens automatically forever.
```

### Bad - Too Detailed Getting Started:
```
### Step 1: Tell Synthia About You

Start a conversation with Synthia. Share what's currently on your mind. Talk about your current projects, things you want to remember, and preferences that matter to you in your daily life.

Just talk naturally, like you would with a friend. Synthia intelligently figures out what's important based on what you're saying and stores it for future reference. (TOO LONG - make it single-line format)
```

### Good - Consolidated Capabilities with Transition:
```
### Access From Anywhere

Start a conversation on your computer, continue on your phone, finish by voice. Same conversation, same memory - like texting a friend. Computer when working, phone when out, voice when hands are full.

Plus: Works with Google Calendar and Gmail. Handles repetitive web tasks. Even creates images when you need them.

Here's how this plays out in real life:

## Real Stories from Real Life
```

### Bad - Separate Capabilities Section:
```
### Extra Capabilities That Make Life Easier

**Search Past Conversations:** Remember that discussion from two months ago? Synthia can pull up the complete transcript...

**Create Images:** Need a quick visual? Describe what you want and Synthia generates it...

**Handle Web Tasks:** Filling out the same form repeatedly?... (TOO VERBOSE - breaks flow, should be consolidated into "Plus:" line)
```

### Good - Comparison Table Tagline (emphasize training):
```
Think of ChatGPT like meeting a helpful stranger daily. Synthia is like training an assistant who learns your way of doing things and never forgets.
```

### Good - Teaching-Focused Testimonial (include at least one):
```
"I taught it my client intake process once. Now it handles new clients exactly how I like. Saves me hours." - Small business owner

"The more I teach it, the better it gets. It's like having an assistant who actually learns." - Freelancer
```

### Good - Strong CTA with Action:
```
## Ready to Stop Repeating Yourself?

You can keep juggling everything in your head, or let Synthia remember it all.

**Get started:** [Download Synthia](#) or visit the documentation to set up your personal AI assistant in minutes.
```

### Bad - Vague CTA:
```
## Ready to Get Started?

Never forget important details. Get automated reminders. Always be prepared.

You can keep juggling everything in your head, or let Synthia remember it all.

Start a conversation. See what it's like to have an assistant who never forgets. (NO ACTIONABLE LINK - where do they go? what's the next step?)
```

## Known Paths

- Architecture doc: `/home/synthia/.claude/data/synthia_architecture.md`
- Skills directory: `/home/synthia/skills/`
- Output location: `/home/synthia/.claude/data/synthia_product.md`

## Example Usage

- "Create marketing content for Synthia"
- "Generate a promotional page"
- "Write marketing copy highlighting Synthia's advantages"
- "Create a product page for Synthia"

## Response to User

After generating the promotional content, respond with:

"Product marketing page complete."

Do not include summaries or explanations - just the completion message.
