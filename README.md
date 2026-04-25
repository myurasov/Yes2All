# Yes2All

Auto-approve agent tool prompts in Cursor / Visual Studio Code via the Chrome DevTools Protocol exposed through `--remote-debugging-port`.

## Quickstart

Launch your editor with the debugging port enabled, e.g.:

```sh
# Cursor
/Applications/Cursor.app/Contents/MacOS/Cursor --remote-debugging-port=9222
```

Then:

```sh
uv sync
uv run yes2all targets --port 9222         # list CDP targets
uv run yes2all probe   --port 9222         # find Run/Allow/Approve buttons
uv run yes2all probe   --port 9222 --click # click the first match
```
