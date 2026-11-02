---
name: analyze-prompt
description: Analyze existing prompt and suggest improvements using the Seven Levels framework
allowed-tools: Read, Glob, Grep, Skill
argument-hint: [prompt-file-path]
---

# Analyze Prompt

Analyze existing prompt and suggest improvements.

## Arguments

- `$1`: Path to prompt file

## Instructions

You are analyzing an existing prompt to classify it and suggest improvements.

### Step 1: Validate Input

If no `$1` provided, STOP and ask user for prompt file path.

### Step 2: Read the Prompt

Read the prompt file at `$1` completely.

### Step 3: Identify Sections

Check for presence of:

- [ ] Frontmatter (metadata)
- [ ] Title
- [ ] Purpose
- [ ] Variables
- [ ] Instructions
- [ ] Workflow
- [ ] Control Flow (conditionals, loops)
- [ ] Delegation (Task tool usage)
- [ ] Template (Specified Format)
- [ ] Expertise
- [ ] Report

### Step 4: Classify Level

Based on sections and patterns:

| Indicators | Level |
| --- | --- |
| Simple prompt, no sections | 1 |
| Has Workflow section | 2+ |
| Has conditionals/loops | 3+ |
| Delegates to agents | 4+ |
| Accepts prompt as input | 5+ |
| Has Template section | 6+ |
| Has Expertise section | 7 |

### Step 5: Analyze Quality

Check:

- [ ] Variables use SCREAMING_SNAKE_CASE
- [ ] Workflow has numbered steps
- [ ] STOP conditions are explicit
- [ ] Frontmatter has description
- [ ] Purpose is clear
- [ ] Report format specified

### Step 6: Identify Improvements

Suggest:

- Missing sections for the level
- Variable naming fixes
- Workflow structure improvements
- Level upgrade opportunities

## Output

```markdown
## Prompt Analysis

**File:** [path]
**Current Level:** [1-7] ([name])

### Sections Found
- [x] Section 1
- [ ] Section 2 (missing)
...

### Quality Score
**Score:** [X/10]

| Criteria | Status |
| --- | --- |
| Variables naming | [Pass/Fail] |
| Workflow structure | [Pass/Fail] |
| STOP conditions | [Pass/Fail] |
| Frontmatter | [Pass/Fail] |
| Purpose clarity | [Pass/Fail] |

### Improvements Suggested

**High Priority:**
1. [improvement 1]
2. [improvement 2]

**Medium Priority:**
1. [improvement 3]

### Level Upgrade Opportunity

Current: Level [N]
Potential: Level [M] if [condition]

### Refactored Version (if requested)

[Improved prompt structure]
```

## Notes

- See @seven-levels.md for level indicators
- See @prompt-sections-reference.md for required sections
- Use /upgrade-prompt to apply suggested improvements
