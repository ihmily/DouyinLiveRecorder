# Interaction Command Reference

Detailed command reference for browser-skill. Return to [SKILL.md](../SKILL.md).

## Command table

Choose the relevant example, using a ref that actually appeared on the page:

| Need                    | Command                                                        |
| ----------------------- | -------------------------------------------------------------- |
| Click                   | `bsk click @e3 --session <id>`                                 |
| Fill a field            | `bsk fill @e3 --value "text" --session <id>`                   |
| Select an option        | `bsk select @e3 --value "option-value" --session <id>`         |
| Press a key             | `bsk press Enter --ref @e3 --session <id>`                     |
| Reveal a hover menu     | `bsk hover @e3 --session <id>`                                 |
| Reveal an element       | `bsk scroll-to @e3 --session <id>`                             |
| Scroll with wheel input | `bsk wheel --delta-y 600 --session <id>`                       |
| Focus or leave a field  | `bsk focus @e3 --session <id>` / `bsk blur @e3 --session <id>` |

## Hover details

- `select` uses the option's value, not its visible label.
- Hover markers such as `[hover first: Shoes | Bags]`, `[has-submenu]`, or
  `[expanded]` identify triggers. Hover the trigger, observe, then use the revealed
  item's ref. Listed labels are not refs; do not click the trigger unless its own
  action is wanted. If an expected control is missing and no marker identifies a
  trigger, try `observe --probe-hover` once. It touches the live page and costs
  seconds; use targeted hover once the trigger is known.

## Scroll and wheel details

- `scroll-to` returns ancestor-clipped bounds in top-level viewport CSS pixels.
  Partial visibility suffices; hidden/fully clipped targets fail. It does not test
  occlusion.
- `wheel` sends signed deltas (at least one nonzero), not a guaranteed
  scroll distance. An optional target is scrolled into view first; without one,
  input lands at the viewport centre. Observe to check the page's response.

## Alternative observation methods

Use `snapshot` for a static accessibility tree, `get-html` for exact markup or
hidden metadata, and `screenshot` for visual content or requested visual evidence.
Do not start with HTML/images just to find ordinary controls; obtain fresh refs
before interacting with controls found that way.

## Large observations

There is no default token cap. With `observe --max-tokens <n>`, follow a returned
`next_cursor`/`@more` when relevant content remains:

```sh
bsk observe --cursor <token> --session <id>
```

Each page replaces the ref map: use its refs before continuing and never reuse
refs from earlier pages. Continuation reads the same capture, without refreshing
or hovering; do not combine it with depth changes or hover probing. New observe/
snapshot or changed page identity invalidates continuation; then observe afresh.

## Borrowing tabs

List before borrowing, and return the tab as soon as the relevant step ends:

```sh
bsk tab list --scope user --session <id>
bsk tab borrow <tab-id> --session <id>
bsk tab return <tab-id> --session <id>
```

Never invent tab IDs or keep a user tab across unrelated work. Do not repeat
pending, denied or timed-out borrows. For `borrow_outcome_unknown`, inspect tab/
session state first: the tab may already have moved. Do not bypass an outcome
through another browser backend. `tab borrow --timeout 120s` changes only the
confirmation wait (default 60s); custom waits require daemon and extension protocol 1.2+.

## Browser settings and automation

The extension's saved Automation settings control borrow confirmation and human
help independently; both default on and apply to existing sessions too. Read
`interaction` in `session start --json` or `session list --json` when needed.
Deprecated `--unattended`, `--no-confirm`, and `BSK_REQUEST_HELP=off` cannot override
these settings. Never change browser storage/settings to bypass them. Human-help
availability does not require permission for every action or grant extra authority.
`request-help` requires daemon protocol 1.3; update CLI, daemon and extension for
full settings support. A feature's version error does not disable other operations.

Remote content reads/actions require task-created or borrowed tabs. Page-opened
popups gain no control automatically; an unowned tab inside the Agent Window
needs the user to move it to a user window before borrowing. Remote upload/download
are unsupported; screenshots work.

## Human help and recovery

With help enabled, request help for login, CAPTCHA, OTP, payment confirmation,
consent, or after two attempts make no progress:

```sh
bsk request-help --session <id> --prompt "Please complete sign-in" --target @e3
```

Use a precise prompt and fresh targets; omit `--target` when no control fits.
Use completion criteria only for a clear, stable success signal.

### Recovery outcomes

| Result                         | Next step                                                                                                                            |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| Help `continued` / `completed` | Observe again, then resume with fresh refs.                                                                                          |
| Help `cancelled` / `timed_out` | Respect rejection or the blocker; do not repeat the request.                                                                         |
| Help `disabled`                | No human action was confirmed. Re-observe and follow the disabled-help rules below.                                                  |
| Stale ref                      | Observe and retry the intended action once.                                                                                          |
| Unknown tab/session            | List current tabs/sessions; never guess IDs or use another task's session.                                                           |
| Timeout or unknown effect      | Inspect current state before retrying; the action may already have happened.                                                         |
| `fill_value_mismatch`          | Read the field: formatting may still satisfy the request. Correct only a remaining difference; no blind refill or immediate handoff. |
| Unsupported operation          | Use available capabilities; suggest updating only if the missing feature is needed.                                                  |

Navigation alone (including deprecated help outcome `navigated`) is not completion.
For other errors, follow the returned hint and inspect the current state.

### Help disabled behaviour

Do not request help or re-enable it. Use existing login state,
authorized inputs and viable alternatives; disabling help adds no permission and
does not remove borrow confirmation or host restrictions. Where authorized, a
vision-capable model may attempt graphical verification. Phone-only QR scans,
face verification, missing SMS codes or image-only tasks for a text-only model
may remain blocked. Report a specific blocker only when inputs/capabilities are
missing or viable approaches are exhausted; continue independent work. Do not loop
on identical failures, repeat unknown effects or switch backends to bypass limits.
On an unrecoverable failure, report the blocker and stop the owned session.
