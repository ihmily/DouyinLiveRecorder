# Editing with ast-grep

ast-grep can rewrite code in addition to searching. Use `--rewrite` for transformations.

## Simple Replacement

```bash
# Preview changes (default - no file modification)
ast-grep run --pattern 'OLD' --rewrite 'NEW' --lang js src/

# Apply changes to files
ast-grep run --pattern 'OLD' --rewrite 'NEW' --lang js src/ --update-all

# Interactive mode (review each change)
ast-grep run --pattern 'OLD' --rewrite 'NEW' --lang js src/ --interactive
```

## Rename Symbol

### All Occurrences

```bash
ast-grep run --pattern 'oldName' --rewrite 'newName' --lang js src/ --update-all
```

### With Structure Preservation

```bash
# Rename function (definition + calls)
ast-grep run \
  --pattern 'function oldName($$$ARGS) { $$$BODY }' \
  --rewrite 'function newName($$$ARGS) { $$$BODY }' \
  --lang js src/ --update-all

# Rename function calls
ast-grep run \
  --pattern 'oldName($$$)' \
  --rewrite 'newName($$$)' \
  --lang js src/ --update-all
```

### Rename Class

```bash
# Rename class definition
ast-grep run \
  --pattern 'class OldClass { $$$BODY }' \
  --rewrite 'class NewClass { $$$BODY }' \
  --lang js src/ --update-all

# Rename instantiations
ast-grep run \
  --pattern 'new OldClass($$$)' \
  --rewrite 'new NewClass($$$)' \
  --lang js src/ --update-all
```

## Replace Function Body

```bash
# Replace entire function
ast-grep run \
  --pattern 'function myFunc($$$ARGS) { $$$BODY }' \
  --rewrite 'function myFunc($$$ARGS) { /* new implementation */ return null; }' \
  --lang js src/ --update-all

# Replace method body
ast-grep run \
  --pattern 'myMethod($$$ARGS) { $$$BODY }' \
  --rewrite 'myMethod($$$ARGS) { return this.newImpl($$$ARGS); }' \
  --lang js src/ --update-all
```

## YAML Rule Files

For complex or reusable queries, use YAML rules:

### Basic Rule

```yaml
# find_functions.yaml
id: find-all-functions
rule:
  pattern: function $NAME($$$) { $$$ }
language: js
```

```bash
ast-grep scan --rule find_functions.yaml path/
```

### Rule with Fix

```yaml
# rename.yaml
id: rename-symbol
language: JavaScript
rule:
  pattern: oldSymbol
fix: newSymbol
```

```bash
ast-grep scan --rule rename.yaml src/ --update-all
```

### Rule with Constraints

```yaml
# Only rename in specific context
id: rename-in-class
language: JavaScript
rule:
  pattern: oldMethod($$$)
  inside:
    pattern: class MyClass { $$$ }
fix: newMethod($$$)
```

### Find Class Methods

```yaml
# class_methods.yaml
id: find-methods
rule:
  pattern: |
    $NAME($$$) {
      $$$
    }
  inside:
    pattern: class $CLASS { $$$ }
language: js
```

## Meta-Variable Transforms

```yaml
id: convert-case
language: JavaScript
rule:
  pattern: const $VAR = $VALUE
transform:
  SNAKE_VAR:
    convert:
      source: $VAR
      toCase: snake_case
fix: const $SNAKE_VAR = $VALUE
```

## Insert Code (Workaround)

ast-grep doesn't have direct insert before/after, but you can:

```bash
# Add decorator/annotation by matching and rewriting
ast-grep run \
  --pattern 'function $NAME($$$) { $$$BODY }' \
  --rewrite '/** @deprecated */
function $NAME($$$) { $$$BODY }' \
  --lang js src/ --update-all
```

## Safety Tips

1. **Always preview first** - Run without `--update-all` to see changes
2. **Use `--interactive`** - Review each change before applying
3. **Narrow scope** - Specify exact path to limit changes
4. **Backup or commit first** - Ensure you can revert
5. **Test after** - Run tests to verify changes

## Comparison: Edit Tool vs ast-grep

| Scenario | Use Edit Tool | Use ast-grep |
|----------|---------------|--------------|
| Single precise edit | ✓ | |
| Bulk rename across files | | ✓ |
| Pattern-based transformation | | ✓ |
| Need to preserve structure | | ✓ |
| Complex multi-line edit | ✓ | |
| Interactive review needed | | ✓ |
