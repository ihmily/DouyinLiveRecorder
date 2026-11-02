# Common Workflows

## Find Definition and All Usages

```bash
# Find where function is defined
ast-grep run --pattern 'function createUser($$$) { $$$ }' --lang js src/

# Find all calls to it
ast-grep run --pattern 'createUser($$$)' --lang js src/
```

## Find All Exports

```bash
# ES6 named exports
ast-grep run --pattern 'export function $NAME($$$) { $$$ }' --lang js src/
ast-grep run --pattern 'export const $NAME = $$$' --lang js src/

# Default exports
ast-grep run --pattern 'export default $$$' --lang js src/
```

## Find Class Hierarchy

```bash
# Find class and its methods
ast-grep run --pattern 'class MyClass { $$$ }' --lang js src/ --json \
  | jq '.[0].text'

# Find classes extending a base
ast-grep run --pattern 'class $NAME extends BaseClass { $$$ }' --lang js src/
```

## Batch Analysis

### Get All Function Names

```bash
ast-grep run --pattern 'function $NAME($$$) { $$$ }' --lang js src/ --json \
  | jq '.[] | .metaVariables.single.NAME.text'
```

### Count Usages

```bash
ast-grep run --pattern 'myFunction($$$)' --lang js src/ --json | jq 'length'
```

### List Files with Pattern

```bash
ast-grep run --pattern '$PATTERN' --lang js src/ --json \
  | jq -r '.[].file' | sort -u
```

## Context and Filtering

```bash
# Show context lines
ast-grep run --pattern 'PATTERN' --lang js -C 3 path/

# Search specific file
ast-grep run --pattern 'PATTERN' --lang js file.js

# Search directory
ast-grep run --pattern 'PATTERN' --lang js src/
```

## JSON Output Fields

```bash
ast-grep run --pattern '$FUNC($$$)' --lang js path/ --json
```

Output includes:
- `text` - Matched code
- `range` - Line/column positions
- `file` - Source file path
- `metaVariables` - Captured meta-variable values

## Performance Tips

1. **Specify language** - `--lang js` avoids parsing wrong files
2. **Narrow path** - `ast-grep run ... src/` vs entire repo
3. **Use `--json=stream`** - For large result sets
4. **Compile rules** - Pre-compile YAML rules for repeated use

## Tool Comparison

| Feature | ast-grep | ripgrep | clj-kondo |
|---------|----------|---------|-----------|
| **Match Type** | AST/structural | Text/regex | Clojure semantic |
| **Languages** | 31 | All text | Clojure only |
| **Accuracy** | High (syntax-aware) | Medium | Very high |
| **Speed** | Fast | Very fast | Fast |
| **Use Case** | Structure search | Content search | Clojure analysis |

Use `code-search` skill (ripgrep) when you need:
- Simple text/regex patterns
- Language-agnostic search
- Maximum speed

Use `code-symbols` (this group's references/code-symbols/SKILL.md, ast-grep) when you need:
- Structural matching (functions, classes)
- Accurate symbol boundaries
- Language-specific patterns
