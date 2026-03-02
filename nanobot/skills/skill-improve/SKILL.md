---
name: skill-improve
description: Improve skill creation through guided discovery. Always active — when the user asks to create, build, or design a new skill, run this discovery process BEFORE creating the skill.
always: true
---

# Skill Improve

When the user requests creating a new skill, **do NOT start building immediately**. First run a structured discovery phase to understand requirements and uncover potential improvements.

## Workflow

### Phase 1: Analysis & Questions

After the user describes what skill they want, analyze their request and ask **exactly 10 questions** in a single message. The questions should cover:

1. **Scope** — What specific tasks should the skill handle? What should it NOT handle?
2. **Trigger** — How should the skill be activated? (user message keywords, always-on, tool call)
3. **Input/Output** — What inputs does the skill expect? What outputs should it produce?
4. **Edge cases** — What happens when inputs are missing, malformed, or unexpected?
5. **Integration** — Does it need external APIs, CLI tools, or specific libraries?
6. **Configuration** — Should any behavior be configurable by the user?
7. **Error handling** — How should failures be communicated?
8. **Examples** — Can the user provide 2-3 concrete usage examples?
9. **Priority** — Which features are must-have vs nice-to-have?
10. **Existing solutions** — Are there existing tools or workflows this should replicate or improve upon?

Adapt these categories to the specific skill being requested. Not every question needs to map to one category — use judgment to ask the most useful questions for the particular skill.

Format:
```
I'd like to ask 10 questions to help build the best possible skill:

1. [question]
2. [question]
...
10. [question]

Answer as many as you'd like — skip any that aren't relevant.
```

### Phase 2: Create the Skill

After receiving the user's answers, combine the original request + all answers to create the skill. Follow these guidelines:

**Choose the right implementation approach for the skill:**

- **Markdown-only** — For skills that provide guidance, workflows, or instructions. No scripts needed. This is the simplest and most common form. Use when the skill is primarily about teaching the agent a procedure.
- **Markdown + shell scripts** — For skills that wrap CLI tools or run specific commands. Use when deterministic shell commands are central to the skill.
- **Markdown + Python scripts** — For skills that need programmatic logic, data processing, or complex integrations. Use `py_writer` for `.py` files. Use when the skill needs reusable code.
- **Markdown + references** — For skills with extensive domain knowledge. Keep SKILL.md lean, put details in `references/`.

**Do NOT default to Python for everything.** Match the implementation to the skill's actual needs. A skill that teaches the agent how to use `curl` for weather data does not need a Python class — markdown instructions are sufficient.

**LOGIC.md is optional.** Only create LOGIC.md when the skill has Python code with non-trivial execution flow. Markdown-only skills and simple script-based skills do not need LOGIC.md.

**Required output:**
- `SKILL.md` with proper frontmatter (`name`, `description`)
- Any scripts, references, or assets identified during discovery
- Brief summary of what was created and how to use it
