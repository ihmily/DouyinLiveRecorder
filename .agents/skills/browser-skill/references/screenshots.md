# Screenshots and Canvas Reference

Detailed screenshot and Canvas reference for browser-skill. Return to [SKILL.md](../SKILL.md).

## Screenshot commands

```sh
bsk screenshot --session <id> --out viewport.png
bsk screenshot --session <id> --ref @e3 --out element.png --json
bsk screenshot --session <id> --full-page --out page.png
bsk screenshot --session <id> --full-page --scope current --out loaded.png
```

Screenshots return a local PNG path; view the image to interpret it. `--out`
replaces an existing file; omitting it uses a temporary path. `--json` includes
dimensions and byte size. `--ref` and `--full-page` cannot be combined.

## Full-page capture details

Full-page mode scrolls an ordinary webpage and restores its position/styles.
The default `--scope follow` follows appended content. Use `--scope current` when
capturing the currently loaded range is requested: it stops at the initial document
height, even if a loading indicator remains. Later content below that boundary is
excluded; report this range rather than claiming all feed entries were loaded.

Use a selected, session-controlled tab and stable viewport; `--tab-id` targets a
tab without selecting it. Internal browser pages, the Web Store, nested scrolling
panels and virtualized lists are unsupported. Capture/encoding defaults to 2m;
`--timeout 5m` extends it only in full-page mode. Allow the shell enough time for
capture plus transfer. Respect cancellation; do not blindly retry endless pages
or substitute a viewport image when an older extension rejects full-page capture.
Use matching CLI/extension builds. Ctrl-C cancels; failed full-page captures save
no partial image.

A `loading_stalled` error means the bottom kept a loading indicator without height
growth for 30s; do not simply increase the deadline. Choose `current` only when
that range satisfies the request. Keep the capture tab visible: `page_hidden` is
an environment interruption, while `user_cancelled` means user input stopped
capture. For other failures follow the returned reason and hint; do not work
around them by editing the page or stitching screenshots.

## Canvas elements

For `@eN canvas [visual:screenshot]`, observe returns text, not pixels. Screenshot
that ref when its contents matter; never infer Canvas controls or names from
nearby labels. If images cannot be received/understood, explain the limitation,
ask for an image-capable model when needed, and continue with available semantics.

## Clicking by screenshot coordinates

To click a point seen in a Canvas image, retain that screenshot's `capture_id`:

```sh
bsk click @e3 --capture <capture-id> --image-x <x> --image-y <y> --session <id>
```

Use ORIGINAL PNG coordinates and dimensions, not resized display/viewport pixels.
Captures are single-use, expire after 2m, and are invalidated by ref replacement
(observe/snapshot/continuation) or a newer screenshot of that ref. With
`capture_unavailable`, the image is view-only: observe and screenshot again before
clicking. Counts 1/2, buttons and modifiers work; Canvas fill, IME, drag, hover
and HTML extraction do not. Repainting is allowed; changed identity/geometry/hit
targets are rejected. Verify the result, using DOM refs for revealed controls;
inspect `effect_state=unknown` before retrying with a new capture.
