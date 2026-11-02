# Language-Specific Patterns

Pattern examples for each supported language.

## JavaScript/TypeScript

### Function Definitions

```bash
# Function declarations
ast-grep run --pattern 'function $NAME($$$) { $$$ }' --lang js path/

# Arrow functions
ast-grep run --pattern 'const $NAME = ($$$) => { $$$ }' --lang js path/

# Async functions
ast-grep run --pattern 'async function $NAME($$$) { $$$ }' --lang js path/

# Class methods
ast-grep run --pattern '$NAME($$$) { $$$ }' --lang js path/
```

### TypeScript-specific

```bash
# Interface definitions
ast-grep run --pattern 'interface $NAME { $$$ }' --lang ts path/

# Type aliases
ast-grep run --pattern 'type $NAME = $TYPE' --lang ts path/
```

### Imports/Exports

```bash
# ES6 imports
ast-grep run --pattern 'import $$$from "module-name"' --lang js path/

# Named exports
ast-grep run --pattern 'export function $NAME($$$) { $$$ }' --lang js path/
ast-grep run --pattern 'export const $NAME = $$$' --lang js path/

# Default exports
ast-grep run --pattern 'export default $$$' --lang js path/
```

### Classes

```bash
# Class definition
ast-grep run --pattern 'class $NAME { $$$ }' --lang js path/

# Class with extends
ast-grep run --pattern 'class $NAME extends $BASE { $$$ }' --lang js path/

# Class instantiation
ast-grep run --pattern 'new $CLASS($$$)' --lang js path/
```

### React Components

```bash
# Function components
ast-grep run --pattern 'function $NAME($$$) { return $$$ }' --lang tsx path/

# Arrow function components
ast-grep run --pattern 'const $NAME = ($$$) => { $$$ }' --lang tsx path/
```

## Python

### Functions

```bash
# Function definitions
ast-grep run --pattern 'def $NAME($$$):' --lang py path/

# Async functions
ast-grep run --pattern 'async def $NAME($$$):' --lang py path/

# Methods (with self)
ast-grep run --pattern 'def $NAME(self, $$$):' --lang py path/
```

### Classes

```bash
# Class definitions
ast-grep run --pattern 'class $NAME:' --lang py path/
ast-grep run --pattern 'class $NAME($$$):' --lang py path/
```

### Decorators

```bash
# Find decorated functions
ast-grep run --pattern '@$DEC
def $NAME($$$):' --lang py path/
```

## Go

### Functions

```bash
# Function definitions
ast-grep run --pattern 'func $NAME($$$)' --lang go path/

# Functions with return type
ast-grep run --pattern 'func $NAME($$$) $RET' --lang go path/

# Methods (with receiver)
ast-grep run --pattern 'func ($RECV $TYPE) $NAME($$$)' --lang go path/
```

### Types

```bash
# Struct definitions
ast-grep run --pattern 'type $NAME struct { $$$ }' --lang go path/

# Interface definitions
ast-grep run --pattern 'type $NAME interface { $$$ }' --lang go path/
```

## Rust

### Functions

```bash
# Function definitions
ast-grep run --pattern 'fn $NAME($$$)' --lang rust path/

# Async functions
ast-grep run --pattern 'async fn $NAME($$$)' --lang rust path/

# Public functions
ast-grep run --pattern 'pub fn $NAME($$$)' --lang rust path/
```

### Types

```bash
# Struct definitions
ast-grep run --pattern 'struct $NAME { $$$ }' --lang rust path/

# Enum definitions
ast-grep run --pattern 'enum $NAME { $$$ }' --lang rust path/

# Trait definitions
ast-grep run --pattern 'trait $NAME { $$$ }' --lang rust path/

# Impl blocks
ast-grep run --pattern 'impl $TYPE { $$$ }' --lang rust path/
```

## Java

### Methods

```bash
# Public methods
ast-grep run --pattern 'public $RET $NAME($$$) { $$$ }' --lang java path/

# Any method
ast-grep run --pattern '$MOD $RET $NAME($$$) { $$$ }' --lang java path/
```

### Classes

```bash
# Class definitions
ast-grep run --pattern 'class $NAME { $$$ }' --lang java path/

# Public class
ast-grep run --pattern 'public class $NAME { $$$ }' --lang java path/
```

## Kotlin

### Functions

```bash
# Function definitions
ast-grep run --pattern 'fun $NAME($$$)' --lang kotlin path/

# Suspend functions
ast-grep run --pattern 'suspend fun $NAME($$$)' --lang kotlin path/
```

### Classes

```bash
# Class definitions
ast-grep run --pattern 'class $NAME { $$$ }' --lang kotlin path/

# Data classes
ast-grep run --pattern 'data class $NAME($$$)' --lang kotlin path/
```
