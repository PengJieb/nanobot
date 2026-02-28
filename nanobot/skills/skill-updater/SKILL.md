---
name: skill-updater
description: List installed skills, check for available updates, or update workspace skills. Use when the user asks to update skills, check skill updates, list installed skills, or manage workspace skill versions.
---

# Skill Updater

Manage workspace skills using the `skill_update` tool.

## Actions

### List installed skills

```
skill_update(action="list")
```

Shows all skills in `workspace/skills/` with name, version, source, and description.

### Check for updates

```
skill_update(action="check")
skill_update(action="check", names=["skill-name"])
```

Queries ClawHub for available updates without installing.

### Update skills

```
skill_update(action="update")
skill_update(action="update", names=["skill-name"], backup=true)
```

Updates ClawHub-sourced skills. Manual skills are skipped. By default creates a timestamped backup before updating.

## Limitations

- Only ClawHub-sourced skills can be auto-updated. Manual skills are skipped.
- Requires Node.js (`npx`) for ClawHub operations.
- Python scripts in updated skills are validated for class-centric structure; warnings are reported but do not block the update.
