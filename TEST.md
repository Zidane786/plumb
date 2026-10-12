# Testing Plumb by hand

Hands-on checks for a machine with Python 3.9+, run in a throwaway project (never in a real one). Each check says
what to do and what you should see.

## Prototype variants (`build-prototype.py --proposal`)

Set up: a project with a design system and at least one screen (e.g. after `/plumb:create`). In it:

1. Make two variants of one screen:
   ```bash
   mkdir -p docs/design/prototype/proposals/demo/a-calm/screens docs/design/prototype/proposals/demo/b-dense/screens
   cp docs/design/prototype/screens/<id>.html docs/design/prototype/proposals/demo/a-calm/screens/
   cp docs/design/prototype/screens/<id>.html docs/design/prototype/proposals/demo/b-dense/screens/
   printf '# Calm\n\nMore space, one action.\n\n- Easy to scan\n- Longer page\n' > docs/design/prototype/proposals/demo/a-calm/idea.md
   ```
   Change a heading in `b-dense/screens/<id>.html` so the two differ.
2. `python3 <skill>/scripts/build-prototype.py --proposal demo`
   **Expect:** `wrote …` lines for `demo/a-calm/prototype.html`, `demo/a-calm/screens.html`, the same two for
   `b-dense`, and `demo/index.html`, then `proposal demo: 2 variants (a-calm: 1 screen, b-dense: 1 screen)`, exit 0.
   `docs/design/prototype/screens.json` is unchanged (`git diff` shows nothing there).
3. Open `docs/design/prototype/proposals/demo/index.html` from disk.
   **Expect:** two cards side by side ("Calm" with its idea and two trade-offs, "B dense"), each with "Clickable
   prototype" and "Every state, light and dark" links that open that variant's pages; the theme toggle switches light
   and dark; nothing is loaded from the network.
4. Run step 2 again. **Expect:** `ok: proposal demo: 2 variants (…): up to date` and no file changed.
5. Edit `b-dense/screens/<id>.html`, then `python3 <skill>/scripts/build-prototype.py --check --proposal demo`.
   **Expect:** exit 1 listing `stale: …/b-dense/prototype.html` and `…/b-dense/screens.html` and a `fix:` line with
   `--proposal demo`.
6. Change a colour in the tokens file and run `python3 <skill>/scripts/build-tokens.py`.
   **Expect:** the proposal pages are rewritten too, and `python3 <skill>/scripts/build-tokens.py --check` exits 0.
7. `python3 <skill>/scripts/build-prototype.py --proposal ../x` and `--proposal missing`.
   **Expect:** exit 2 with an `error:` line and a `fix:` line each; nothing written.
