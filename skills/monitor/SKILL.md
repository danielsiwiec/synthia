---
description: Monitor a condition, state, or value by scheduling periodic checks. Use when user asks to watch, monitor, track, alert when, notify when, let me know when, or wait until something happens.
---

# Monitor Skill

Set up background monitoring for any condition, state, or value. When the condition is met, sends a notification and automatically cleans up.

## Overview

This skill creates a silent scheduled job that periodically checks a user-defined condition. Once the condition is satisfied, it:
1. Notifies the admin about the event
2. Deletes the monitoring job (self-cleanup)

## How It Works

1. **User specifies what to monitor** - a condition, value, or state to track
2. **Create a unique job name** - use format `monitor-<descriptive-name>` (e.g., `monitor-sauna-temp`, `monitor-download-complete`)
3. **Schedule a silent job** every 60 seconds
4. **Job task includes**:
   - The check to perform
   - The success condition
   - Notification message when condition is met
   - Self-deletion instruction

## Creating a Monitor

Use the `mcp__scheduler__add-job` tool with these parameters:

```
name: monitor-<descriptive-name>
seconds: 60
start_date: <current time + 60 seconds in ISO format>
silent: true
task: <detailed task description - see template below>
```

### Task Template

The task description should follow this pattern:

```
Check <what to check>.
If <success condition>, notify admin "<notification message>" and delete the monitor-<name> job.
If <failure/abort condition>, delete the job without notifying.
```

## Examples

### Example 1: Monitor Sauna Temperature

When user says: "Let me know when the sauna reaches 80°C"

```
name: monitor-sauna-temp
seconds: 60
start_date: 2024-01-15T10:01:00Z
silent: true
task: Check sauna temperature using the sauna-controls skill. If current_temp >= 80, notify admin "🔥 Sauna has reached 80°C and is ready!" and delete the monitor-sauna-temp job. If heater is off, delete the job without notifying.
```

### Example 2: Monitor Download Completion

When user says: "Alert me when my torrent finishes downloading"

```
name: monitor-torrent-abc123
seconds: 60
start_date: 2024-01-15T10:01:00Z
silent: true
task: Check torrent status for hash abc123 via qBittorrent API. If state is "completed" or "seeding", notify admin "✅ Torrent 'Movie Name' has finished downloading!" and delete the monitor-torrent-abc123 job. If torrent is removed/not found, delete the job without notifying.
```

### Example 3: Monitor Website Availability

When user says: "Watch if example.com comes back online"

```
name: monitor-example-site
seconds: 60
start_date: 2024-01-15T10:01:00Z
silent: true
task: Check if https://example.com is accessible (HTTP 200 response). If site is reachable, notify admin "🌐 example.com is back online!" and delete the monitor-example-site job.
```

### Example 4: Monitor Price Drop

When user says: "Track this product and tell me if it drops below $100"

```
name: monitor-product-price
seconds: 60
start_date: 2024-01-15T10:01:00Z
silent: true
task: Check the price of [product URL]. If price < $100, notify admin "💰 Price alert! [Product name] is now $XX (below $100)!" and delete the monitor-product-price job.
```

### Example 5: Monitor Email Arrival

When user says: "Let me know when I get an email from john@example.com"

```
name: monitor-email-from-john
seconds: 60
start_date: 2024-01-15T10:01:00Z
silent: true
task: Search Gmail for new unread emails from john@example.com received in the last 2 minutes. If found, notify admin "📧 New email from john@example.com: [subject]" and delete the monitor-email-from-john job.
```

## Managing Monitors

### List Active Monitors
```
Use mcp__scheduler__list-jobs to see all active monitors (they start with "monitor-")
```

### Cancel a Monitor
```
Use mcp__scheduler__delete-job with the monitor name to stop monitoring
```

### Trigger Immediate Check
```
Use mcp__scheduler__trigger-job with the monitor name to check immediately
```

## Best Practices

1. **Use descriptive job names** - Makes it easy to identify and manage monitors
2. **Include abort conditions** - Always specify when to silently delete the job (e.g., if the thing being monitored no longer exists)
3. **Use silent: true** - Prevents notification spam from routine checks
4. **Include context in notifications** - Add relevant details (current value, product name, etc.)
5. **Use appropriate emojis** - Makes notifications visually distinctive

## Example Usage Phrases

- "Monitor the sauna and tell me when it's ready"
- "Watch my download and notify me when it's done"
- "Track this price and alert me if it drops"
- "Let me know when the website is back up"
- "Notify me when I get an email from [person]"
- "Alert me when the temperature reaches [value]"
- "Keep an eye on [thing] and tell me when [condition]"
