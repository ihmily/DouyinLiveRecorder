# Files and Other Tools Reference

Detailed file operations and tool reference for browser-skill. Return to [SKILL.md](../SKILL.md).

## Upload

```sh
bsk upload @e3 --file ./report.pdf --session <id>
```

Upload discloses the file to the site. Use agent-local paths, not browser-internal
staging paths.

- Default upload clicks an upload button/label and intercepts its file chooser.
- If `reason=file_input_not_activated` and `effect_state=none`, re-observe. Try
  `--mode drop` once only on a clear attachment target such as a drop zone or
  composer, never whitespace or an ambiguous container. Otherwise follow the
  human-help rules. There is no automatic fallback between mechanisms.
- Never retry or switch upload modes for `effect_state=unknown` or `committed`.
  A successful drop proves dispatch, not site acceptance; observe the attachment.

## Download

```sh
bsk download @e3 --out ./report.pdf --session <id>
```

Download accepts site-controlled bytes. Use agent-local paths, not browser-internal
staging paths. Download refuses overwrite by default; add `--overwrite` only when
replacement is intended. Consult each command's help for other flags.

## Console and network diagnostics

Use `console` / `network` for bounded read-only diagnostics; follow returned
sequence cursors.

## Device emulation

`emulate --device iphone-14` affects one tab; `--off` restores it.

## JavaScript evaluation

`evaluate` is a last resort: inspect JSON `.ok`, since a script exception can have
CLI exit code 0. Never evaluate secrets.

## Action recording

`record start` captures user actions; read its help first and never record banking,
SSO or password-manager pages.

## Other commands

Use `bsk --help` to find navigation/history, tab, wait and window commands.
