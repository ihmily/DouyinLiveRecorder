---
name: browser-skill
version: 1.1.0
display_name: BrowserSkill
display_name_en: BrowserSkill
description: |
  Use when the user asks to automate their logged-in Chromium browser: visit
  and read pages, fill forms, scrape data, click through flows, regression-test
  a PR's UI, validate a deployed page, or operate a tab they identify. Requires
  the bsk CLI and browser extension.
description_en: |
  Use when the user asks to automate their logged-in Chromium browser: visit
  and read pages, fill forms, scrape data, click through flows, regression-test
  a PR's UI, validate a deployed page, or operate a tab they identify. Requires
  the bsk CLI and browser extension.
description_zh: |
  BrowserSkill 是腾讯开源的一个智能浏览器自动化工具，让 WorkBuddy 能够像人一样操作网页——自动填表、点击、翻页、截图，完成任何需要浏览器的复杂任务。
---

# browser-skill

Use `bsk` to work in an **Agent Window** with the user's existing logins. User tabs
require explicit borrowing. This skill does not install the extension or handle
advice-only tasks. Never extract credentials, cookies, tokens, or other secrets.

## Contents

- [Before starting a session](#before-starting-a-session)
- [Task workflow](#task-workflow)
- [Read and interact](#read-and-interact)
- [Borrowing and browser settings](#borrowing-and-browser-settings)
- [Human steps and recovery](#human-steps-and-recovery)
- [Screenshots and Canvas](#screenshots-and-canvas)
- [Files and other tools](#files-and-other-tools)
- [Detailed references](#detailed-references)

## Before starting a session

For remote setup or pairing, follow the [remote guide](https://github.com/Tencent/BrowserSkill/blob/main/docs/remote-extension-connection.md).

Local commands normally auto-start the daemon. If the host terminates background
children after each shell call, including on Windows, complete these steps first:

1. Reuse the host daemon's existing `BSK_HOME` (or its default if unset). Set
   `BSK_AUTO_START=0` and run `bsk status --json`. Reuse a working daemon; an empty
   `browsers` list means the extension still needs connecting.
2. Only if the check reports a missing daemon and no host task is already starting
   it, run `bsk daemon start --foreground` with the same `BSK_HOME` in the host's
   approved persistent background task outside the per-command sandbox.
3. After launching, run `bsk status --json` in a **separate shell tool call** with
   the same `BSK_HOME` and `BSK_AUTO_START=0`. Make at most five checks with
   one-second pauses; stop on permission/protocol errors.

Use the same `BSK_HOME` and `BSK_AUTO_START=0` on EVERY sandboxed command.
For other startup failures, retry once, then use `bsk doctor`.

## Task workflow

1. Define success from the user's request. Start `bsk session start --json` and
   retain its `session_id`. With multiple browsers, run `bsk browsers` and add
   `--browser <id-or-label>` to start. For background work, add `--no-focus`.
2. For a new page, navigate; for an existing user tab, follow **Borrowing** below.
   Read the page before interacting.
3. Choose an action using fresh refs from that observation. Observe again after
   navigation or meaningful DOM changes. Check an ambiguous result once; once
   success is visible, stop acting.
4. Always run `bsk session stop <id>` on success and failure, unless keeping the
   session open is part of the user's request. This also returns borrowed tabs.

Replace `<id>`, example refs and values with actual results and task inputs.
Every session-scoped command needs `--session <id>`; `session stop` takes the ID
positionally. For unfamiliar commands, consult `bsk --help` instead of guessing.

## Read and interact

Prefer `observe` for text, controls and `@eN` refs. Navigation invalidates refs;
large DOM changes can stale them too. Re-observe before the next interaction.
Use refs for iframe/shadow-root targets; CSS selectors search the main document.

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

- `select` uses the option's value, not its visible label.
- Hover markers (`[hover first]`, `[has-submenu]`, `[expanded]`) identify triggers.
  Hover the trigger, observe, then use the revealed item's ref.
- Use `snapshot` for accessibility tree, `get-html` for markup, `screenshot` for
  visual content. Obtain fresh refs before interacting with controls found that way.
- With `observe --max-tokens <n>`, follow `next_cursor`/`@more` when content remains.
  Each page replaces the ref map; never reuse refs from earlier pages.

> Full details: [references/interact.md](references/interact.md)

## Borrowing and browser settings

```sh
bsk tab list --scope user --session <id>
bsk tab borrow <tab-id> --session <id>
bsk tab return <tab-id> --session <id>
```

- Never invent tab IDs or keep a user tab across unrelated work.
- The extension's Automation settings control borrow confirmation and human help
  independently; both default on. Never change browser storage/settings to bypass them.
- Remote upload/download are unsupported; screenshots work.

> Full details: [references/interact.md](references/interact.md)

## Human steps and recovery

With help enabled, request help for login, CAPTCHA, OTP, payment, consent, or
after two attempts make no progress:

```sh
bsk request-help --session <id> --prompt "Please complete sign-in" --target @e3
```

| Result                         | Next step                                                        |
| ------------------------------ | ---------------------------------------------------------------- |
| Help `continued` / `completed` | Observe again, then resume with fresh refs.                      |
| Help `cancelled` / `timed_out` | Respect rejection; do not repeat.                                |
| Help `disabled`                | Use existing login state and viable alternatives only.            |
| Stale ref                      | Observe and retry once.                                          |
| Unknown tab/session            | List current tabs/sessions; never guess IDs.                     |
| Timeout or unknown effect      | Inspect current state before retrying.                           |

**Help disabled:** do not request help or re-enable it. Report a specific blocker
only when inputs/capabilities are missing or viable approaches are exhausted.

> Full details: [references/interact.md](references/interact.md)

## Screenshots and Canvas

```sh
bsk screenshot --session <id> --out viewport.png
bsk screenshot --session <id> --ref @e3 --out element.png --json
bsk screenshot --session <id> --full-page --out page.png
```

- `--ref` and `--full-page` cannot be combined. `--out` replaces existing files.
- Full-page mode: `--scope follow` (default) follows appended content;
  `--scope current` stops at initial document height.
- For Canvas elements, observe returns text not pixels; screenshot the ref instead.
- Click by screenshot coordinates requires retaining the `capture_id`; captures
  expire after 2m and are invalidated by ref replacement.

> Full details: [references/screenshots.md](references/screenshots.md)

## Files and other tools

```sh
bsk upload @e3 --file ./report.pdf --session <id>
bsk download @e3 --out ./report.pdf --session <id>
```

- Upload discloses the file to the site; download accepts site-controlled bytes.
- Use agent-local paths, not browser-internal staging paths.
- `evaluate` is a last resort; never evaluate secrets.
- `record start`: never record banking, SSO or password-manager pages.

> Full details: [references/files-tools.md](references/files-tools.md)

## Detailed references

| Reference file | Contents |
| --- | --- |
| [references/interact.md](references/interact.md) | Command table, hover/scroll details, borrowing, browser settings, human help and recovery |
| [references/screenshots.md](references/screenshots.md) | Screenshot modes, full-page capture, Canvas elements, coordinate clicking |
| [references/files-tools.md](references/files-tools.md) | Upload/download, console/network, emulation, evaluation, recording |

## 验证

本 Skill 是外部工具技能（`bsk` CLI + 浏览器扩展），不修改项目源码，无对应的项目级门禁。

完成判据：

1. 任务成功：`bsk session stop` 正常返回、借用的标签页已归还。
2. 任务失败：已按「Human steps and recovery」表格处理，未遗留未关闭的会话。
3. 安全：未提取或暴露 Cookie / token 等凭据。
