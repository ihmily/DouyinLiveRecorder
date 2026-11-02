---
name: code-symbols
description: Find and edit symbols in code using ast-grep (tree-sitter based). Use when finding function definitions, class definitions, symbol usages, renaming symbols, or replacing code in JavaScript, TypeScript, Python, Go, Rust, and other languages. NOT for Clojure - use clj-symbols instead.
allowed-tools: Bash, Read, Edit, Task
---

# Code Symbols Skill

Use **ast-grep (`sg`)** for structural code search based on tree-sitter parsing. Works with 31 languages.

**Important:** Clojure is NOT supported. Use the `clj-symbols` skill for Clojure code.

## Prerequisites

```bash
# npm
npm install --global @ast-grep/cli

# Homebrew
brew install ast-grep

# Cargo
cargo install ast-grep --locked
```

Verify: `ast-grep --version` or `sg --version`

## Supported Languages

| Category | Languages |
|----------|-----------|
| **Web** | JavaScript, TypeScript, HTML, CSS, JSON |
| **Systems** | C, C++, Go, Rust |
| **Scripting** | Python, Ruby, PHP, Lua, Bash |
| **JVM** | Java, Kotlin, Scala |
| **Other** | Swift, Haskell, Elixir, Nix |

**Not supported:** Clojure, Erlang, R, MATLAB

## Quick Reference

| Task | Command |
|------|---------|
| Find pattern | `ast-grep run --pattern 'PATTERN' --lang LANG path/` |
| Find with JSON | `ast-grep run --pattern 'PATTERN' --lang LANG path/ --json` |
| Rename symbol | `ast-grep run --pattern 'old' --rewrite 'new' --lang LANG path/ --update-all` |

## Pattern Syntax

Patterns must be **valid code** that tree-sitter can parse.

### Meta-Variables

| Syntax | Meaning | Example |
|--------|---------|---------|
| `$NAME` | Match single node | `function $NAME() {}` |
| `$$$` | Match zero or more nodes | `function foo($$$)` |
| `$_` | Match but don't capture | `$_($$$)` |

### Basic Examples

```bash
# Match any function call
ast-grep run --pattern '$FUNC($$$)' --lang js path/

# Match specific function
ast-grep run --pattern 'myFunction($$$)' --lang js path/

# Match variable assignment
ast-grep run --pattern 'const $NAME = $VALUE' --lang js path/
```

## Common Operations

### Find Function Definition

```bash
# JavaScript
ast-grep run --pattern 'function $NAME($$$) { $$$ }' --lang js path/

# Python
ast-grep run --pattern 'def $NAME($$$):' --lang py path/

# Go
ast-grep run --pattern 'func $NAME($$$)' --lang go path/
```

### Find Symbol Usages

```bash
ast-grep run --pattern 'myFunction($$$)' --lang js path/
ast-grep run --pattern '$OBJ.myMethod($$$)' --lang js path/
```

### Rename Symbol

```bash
# Preview
ast-grep run --pattern 'oldName' --rewrite 'newName' --lang js src/

# Apply
ast-grep run --pattern 'oldName' --rewrite 'newName' --lang js src/ --update-all

# Interactive
ast-grep run --pattern 'oldName' --rewrite 'newName' --lang js src/ --interactive
```

### JSON Output

```bash
ast-grep run --pattern '$FUNC($$$)' --lang js path/ --json
```

Parse with jq:
```bash
ast-grep run --pattern 'function $NAME($$$) { $$$ }' --lang js path/ --json \
  | jq '.[] | {name: .metaVariables.single.NAME.text, file, line: .range.start.line}'
```

## When to Use ast-grep vs ripgrep

| Scenario | Tool |
|----------|------|
| Find by **name** (text pattern) | ripgrep (`rg`) |
| Find by **structure** (function, class) | ast-grep |
| Language-specific patterns | ast-grep |
| Maximum speed | ripgrep |
| Accurate symbol boundaries | ast-grep |

## Additional References

- **Language patterns**: See [references/languages.md](references/languages.md) for JS, TS, Python, Go, Rust patterns
- **Editing**: See [references/editing.md](references/editing.md) for rewrite, rename, and YAML rules
- **Workflows**: See [references/workflows.md](references/workflows.md) for common workflows
