# Per-release upgrade steps

One file per plugin version that needs more than "replace the design-system scripts and templates":
`<version>.md`, e.g. `1.1.0.md`. `/plumb:upgrade` executes them; people can read them too.

## How `/plumb:upgrade` uses them

1. Before changing anything it notes the project's Plumb version (**OLD**, from the first line of
   `PLUMB.md`) and picks every file here whose version is **greater than OLD and at most the
   plugin's version**, in ascending version order (compare as numbers: 1.10.0 > 1.9.0). A project
   going from 1.0.0 to 1.2.0 uses `1.1.0.md` and `1.2.0.md` if they exist.
2. It shows the user each file's **"What's new"** section and asks before upgrading.
3. The general upgrade runs: it replaces the project's copies of the generator, audit and
   prototype scripts and templates, and migrates the tokens file if the schema changed.
4. Then it runs each file's steps, file by file, in their numbered order. Each step is skipped
   when its **check** says it isn't needed, so re-running an upgrade is safe.
5. It records one dated line in `PLUMB.md`'s `## Plumb updates`, runs the checks until there are
   no problems, and repeats a short "What's new" summary at the end.

Agents learn the new commands without any of this: skills, `reference/` and the templates ship
inside the plugin, so a plugin update changes their instructions at once. These files are for the
**project's** files and settings.

## Format of a file

```markdown
# Upgrade to X.Y.Z

## What's new

Plain words for the user: what they can now do, one example command each.

## Steps

One paragraph: when these steps run.

### 1. Short title
**Check:** how to tell it's needed: a command and the output that means "needed", or a file that
lacks a line.
**Do:** exact commands, and the exact questions to ask the user (one at a time, with the
default). Say what to write where.
```

Rules for writing steps:

- Commands use the project's Python command from `PLUMB.md`. Never hand-edit a generated file;
  regenerate it with the project's tokens command.
- Ask before anything that changes meaning or touches files the project owns (`.gitignore`,
  `PLUMB.md`, `AGENTS.md`, `Makefile`, git config). Keep every value the project already set.
  Recommendations are applied only on a yes; the default is "keep".
- Never commit, push or delete data. Plumb never installs or downloads anything: if something is
  missing, ask the user and wait. The upgrade skill shows the diff and the user commits.
- Every step must be idempotent: its check must come back "not needed" once done.
