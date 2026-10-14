# Using Plumb: the complete guide

Plumb keeps a project's design true. It gives your project **one design system** that every screen is built
from, a **clickable prototype** of the whole product that you approve before anything is built, and **checks**
that stop an agent from drifting off the system while it works. It runs in Claude Code and GitHub Copilot CLI
(and Kiro, see below), on macOS, Linux and Windows, and it always asks you before it decides or writes anything.

This guide teaches every part of it. Read "Start here" first; after that, jump to what you need.

- [Start here](#start-here): install, your first `/plumb:init`, updating
- [Walkthroughs by situation](#walkthroughs-by-situation): new project, existing app, monorepo, separate frontend,
  linked repos, opened in the wrong folder, design only
- [Every command](#every-command): when to use it, what it asks, what it changes, an example session
- [The daily loop: prototype first](#the-daily-loop-prototype-first)
- [Prototypes, the screens catalogue, variants and approval](#prototypes-the-screens-catalogue-variants-and-approval)
- [Tours: guide mode and play mode](#tours-guide-mode-and-play-mode)
- [The design-system files and who owns them](#the-design-system-files-and-who-owns-them)
- [Hooks: what they check, what they say, how to switch them](#hooks-what-they-check-what-they-say-how-to-switch-them)
- [Plumb's own mistakes: the feedback log](#plumbs-own-mistakes-the-feedback-log): what gets recorded, how to read
  findings
- [Teams and enterprises](#teams-and-enterprises)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)

A picture of what a project ends up with: [what-you-get.html](what-you-get.html) (open it from disk; it works
offline).

---

## Start here

### What you need

- **Python 3.9 or newer** with its standard library. Plumb installs nothing else: no npm, no pip packages.
  On Windows any of `py -3`, `python` or `python3` works.
- **Claude Code** or **GitHub Copilot CLI**. (Kiro: see below.)
- **git** is optional. With it, Plumb knows the repository root, records who approved a screen and sees exactly which
  files changed in a session. Without it, Plumb still works, with fewer details.

Optional, each with a fallback: the Effective HTML skills (better-looking directions and prototypes; otherwise
Plumb's own templates), a browser (screenshots in `/plumb:audit` and `/plumb:ux`; otherwise they review code), `make`
(otherwise the plain commands in `PLUMB.md`), and Slate (tickets for findings; otherwise none).

### Install in Claude Code

In a terminal:

```
claude plugin marketplace add Zidane786/plumb
claude plugin install plumb@plumb
```

Or inside Claude Code:

```
/plugin marketplace add Zidane786/plumb
/plugin install plumb@plumb
```

Start a new session (or run `/reload-plugins`). Type `/plumb` and you see the eleven commands.

To try a local copy of the repository instead (for example a fork your organisation reviewed):

```
claude --plugin-dir /path/to/plumb/plugins/plumb
```

### Install in GitHub Copilot CLI

The same plugin works in Copilot CLI: the same skills, hooks and commands.

```
copilot plugin marketplace add Zidane786/plumb
copilot plugin install plumb@plumb
```

Then restart Copilot CLI (`/restart`, or quit and start it again). The commands are the same: `/plumb:init`,
`/plumb:create`, and so on. VS Code's Copilot Chat is not supported.

### Kiro (built from Kiro's docs; live check pending)

Plumb's skills follow the Agent Skills standard, so Kiro (IDE and CLI v3+) can run them. Kiro has no plugin
marketplace, so a script copies them in. With Plumb installed in Claude Code or Copilot CLI (or a clone of the Plumb
repository), run it yourself, one scope at a time:

```
python3 <plumb>/plugins/plumb/scripts/kiro.py install                       # your home folder only (~/.kiro)
python3 <plumb>/plugins/plumb/scripts/kiro.py install --project <folder>    # that workspace only (<folder>/.kiro)
python3 <plumb>/plugins/plumb/scripts/kiro.py uninstall [--project <folder>]
```

Each run writes `.kiro/skills/plumb-<name>/SKILL.md` for every command and `.kiro/hooks/plumb.json` in that one scope
(`--project` is that workspace only; it never also writes your home folder). It lists every path first and asks
`[y/N]`; `--yes` skips the question. Run without a terminal (by an agent) and without `--yes`, it writes nothing and
says `ask the user: run … --yes yourself, or tell me to run it`: an agent never confirms for you. It never overwrites
a file it didn't write, or writes through a symlink (`.kiro` itself included). `--home DIR` names another folder that
holds `.kiro` instead of your home (not with `--project`). `uninstall` removes only the files `kiro.py` installed in
that scope. Every flag and what differs in Kiro: [reference/kiro.md](../plugins/plumb/reference/kiro.md).

In Kiro the commands are `/plumb-init`, `/plumb-create`, `/plumb-prototype`, and so on (Kiro skill names can't hold
`:`), and every hook message names them that way. Kiro reads `AGENTS.md` as steering, so Plumb's "read before you
work" row applies there too, and `/plumb-init` can add `.kiro/steering/plumb.md`. **After updating the Plumb plugin,
run `install` again**: the copies point at one plugin folder, and Kiro's session line says when a newer Plumb sits next
to it. If that folder is gone, every hook allows everything and the session line says the checks are off until you
run `kiro.py install` again.

This support was built from Kiro's documented formats and is tested in CI with Kiro-shaped input. **The live check on
a real Kiro install is still pending**: treat it as a preview until a release note says it was verified.

### Your first `/plumb:init`

Open a session **in your project folder** and run:

```
/plumb:init
```

Plumb looks at the folder (it never assumes the folder you opened is the project), goes through the project itself
(manifests, routes, layouts, theme provider, global CSS, `components.json`, fonts, icons, `.gitignore`, existing design
docs), then asks you to confirm what it found and what it will create:

```
Plumb found:
  project    ~/Projects/acme          (git root; you opened ~/Projects/acme/apps/web)
  layout     monorepo (pnpm workspaces)
  UI         apps/web   Next.js · Tailwind v4 · shadcn   (142 UI files → extract)
  no UI      apps/api   FastAPI
I'll create:
  .claude/skills/acme-design-system/   in ~/Projects/acme
  PLUMB.md                             in ~/Projects/acme
  docs/design/                         in ~/Projects/acme   (directions or extract page, decision log, prototype, reports)
  generated copy → apps/web/app/globals.css
    apps/web/app/globals.css exists: Plumb adds and owns only a marked plumb:start … plumb:end block; the rest stays yours
  UI files   apps/web/app/**, apps/web/components/** · *.tsx *.jsx *.css   (142 files match; what the audit and the checks cover)
  routes     apps/web/app (next-app)   (18 pages)
OK, or change something?
```

Each route folder is recorded with its kind, the framework the agent found: `apps/web/app (next-app)`, `src/pages
(next-pages)`, `pages (nuxt)`, `src/routes (sveltekit)`, `src/app (angular)`, a router file such as
`src/router/index.ts (router)`, or `none` for a mobile-only, backend-only or design-only project. Plumb never guesses
the kind from a folder name.

**What you confirm is inside the question.** The whole block is the question itself (or the recommended option's
preview), never only text printed before it: Claude Code can hide a message written just before a question, so Plumb
never relies on one. The same goes for every later checkpoint: the summary, the token set, the file list, a diff, a
mapping. If a question ever asks you to confirm something you can't see, answer "show it" first.

**Detection is a first guess. Plumb shows it, and you confirm.** Plumb's detection only looks for well-known marker
files (package manifests, monorepo configs, stylesheets, Xcode and Gradle projects), and no script knows every layout.
So the agent always investigates too and **checks what the script said**: it counts the files each UI-file pattern
really matches, checks that each route folder exists, and corrects what is wrong, marking it `(corrected: <why>)` with
the evidence (`file:line`, file counts). Facts the code answers are shown as `found: … (file:line)` for you to OK;
only what the code can't tell (who it's for, the feel, your brand) is asked as a question. It always shows you the
block above, even when it is sure, and nothing it found is used until you confirm it.

**Plumb's scripts read what you confirmed; they don't guess your layout.** What you confirm (the UI packages, the UI
files, the route folders, the copies, the allowed raw paths) is recorded in `PLUMB.md` (`UI files:`, `Routes:`, …),
and the audit and the hooks read only that. `scaffold.py --verify` checks it still holds (each route folder exists,
each UI-file pattern matches a file; an `Allowed raw values:` pattern that matches nothing is a warning). When you give
no allowed paths, Plumb defaults them to your UI package's primitives folder (e.g. `web/src/components/ui/**`). Change
it later with `/plumb:update` (or `/plumb:init` again). The same holds for every script's output (the inventory, the overrides mapping, contrast fixes, audit findings): **scripts give
evidence, not answers**, and the agent verifies it before showing it to you.

**A git-ignored skill folder.** If git ignores the place the skill would go (a common `.claude/` line in
`.gitignore`, `.git/info/exclude` or your global excludes file), the design system would never be committed. Init
shows the file and line that ignore it and asks: un-ignore the skill folder in that file (recommended; git can't
re-include a folder whose parent is ignored, so `.claude/` becomes `.claude/*` + `!.claude/skills/`, and `.claude/**`
gets `!.claude/skills/` + `!.claude/skills/**`; for a global excludes file, which applies to every repo, adding
`!.claude/`, `.claude/*` and `!.claude/skills/` to this repo's `.gitignore` also works) or put the system somewhere
else. It checks again after the change and never goes on silently.

Say OK, or correct anything: the folder, the skill's name or place, the UI packages, the copy path, the UI files (which
files the audit and the checks treat as UI) or the docs folder. What you confirm is
written into `PLUMB.md`, so no later command guesses again.

Then init asks whether the project is **new** (no UI yet, so `/plumb:create`) or **existing** (UI code already there,
so `/plumb:extract`), with the one it detected marked "(Recommended)". It runs that flow, then wires Plumb in, asking
about each item on its own: `PLUMB.md`, the row in `AGENTS.md`/`CLAUDE.md`, the Makefile targets, the two checks, the
Slate review check (when Slate is set up) and Kiro steering (when you use Kiro). It asks about the row and the Makefile
even when those files don't exist yet (then the question is whether to create them).

When it finishes, **commit the files** and **start a new session** in the project folder so the hooks load.

### How every command behaves

- **One question at a time**, through the tool's question picker, with options and the recommended one first, marked
  "(Recommended)", and a reason.
- **Nothing is written without your OK.** Every command says what it will write and where, and waits. Create and
  extract are numbered checkpoints; each one stops and waits for your answer, and a permission prompt from your tool
  (Copilot CLI asks before commands) never counts as that answer.
- **What you confirm is inside the question**, in full (not printed above it), with the evidence for each suggestion.
- **Scripts give evidence, not answers.** The agent checks every script result against your code and marks what it
  corrected or added before you decide.
- **Temporary files stay in your project**, in `.plumb-tmp/` (ignored by version control), never in `/tmp` or next to
  the repo. Create and extract also put a marker file there, `.plumb-tmp/setup-in-progress`, from the placement OK
  to the end of setup (the end-of-turn check stands down while it exists), then remove the whole folder last;
  `/plumb:init` treats a leftover marker as a half-finished setup and offers to resume. Other commands may keep
  scratch files there and clean up their own; they never write the marker.
- **Nothing is installed or downloaded.** If something seems missing (a package, a font, a browser), Plumb says what
  and why, asks you, and waits for your decision. It never decides on your behalf.
- **Heavy flows run only when you type them:** `/plumb:init`, `/plumb:create`, `/plumb:extract`, `/plumb:update` and
  `/plumb:upgrade`. Other commands may *offer* them, never start them.
- **Every error is actionable:** `error: <what went wrong>` followed by `fix: <the exact command>` or
  `ask the user: <the question>`.
- **When Plumb itself gets something wrong** (a script, a hook or a skill) and the agent corrects it, the agent
  records that Plumb mistake with `/plumb:feedback`, in `~/.plumb/feedback/` on your machine, outside the project
  ([the feedback log](#plumbs-own-mistakes-the-feedback-log)). Your project's own design issues stay with
  `/plumb:audit`.

### Updating Plumb

**Turn on auto-update once** (Claude Code): run `/plugin`, open the **Marketplaces** tab → **plumb** → **Enable
auto-update**. Or update by hand:

```
claude plugin marketplace update plumb
claude plugin update plumb@plumb
/reload-plugins
```

Copilot CLI: `copilot plugin marketplace update plumb`, then `copilot plugin update plumb@plumb`, then `/restart`.

Then, in each project, run `/plumb:upgrade` (see [its section](#plumbupgrade)). The session-start line tells you when a
project is older than the plugin. Upgrade never runs by itself.

---

## Walkthroughs by situation

### A new project (nothing built yet)

1. Open a session in the project folder (an empty folder is fine; git is optional, init offers `git init` once).
2. `/plumb:init` → confirm the "Plumb found … I'll create …" block → choose **Create a new design system**.
3. `/plumb:create` runs: the product questions, the platforms, each design decision, then 2–3 directions on one page
   (`docs/design/directions.html`). Pick one or combine them.
4. You approve the full token set (light and dark), then the list of files; Plumb writes the design system, computes
   contrast and asks about each fix, writes the starter components in your framework, and checks they pass the audit.
5. It offers to prototype your key screens: each comes as 2–3 variants; you pick and approve one.
6. Every choice is recorded in `docs/design/decisions.md`. Commit, start a new session, and build screens to match the
   prototype.

### An existing app

1. Open a session at the repository root. `/plumb:init` → confirm the block → **Extract the system you already have**.
2. `/plumb:extract` asks which folders hold the UI (and what to leave out, such as vendored or legacy code), then lists
   every colour, font, size, spacing, radius, shadow, duration and easing in use, with counts and `file:line`.
3. Near-duplicates are grouped (colours closer than ΔE 3 and only within one source: a named CSS variable, a Tailwind
   palette class or any other value; sizes within 1px or 6%); a Tailwind `rounded-*` class counts at the project's own
   `@theme` radius (a `--radius` base with `calc()` steps), Tailwind's default only for a size it doesn't define;
   the most-used value of each group
   becomes the proposed token. A before/after page (`docs/design/extract.html`) shows it; you confirm group by group:
   accept, rename, merge, split or leave out.
4. It asks only the product and UX questions the code can't answer, generates the same design system as create, and
   builds the **main prototype from your existing routes** (every route becomes a screen file, marked "synced from
   code" for you to confirm later).
5. Last, it audits what doesn't match yet and offers `/plumb:audit fix` or Slate tickets. Nothing in your app changes
   without your OK.

### A monorepo

Plumb puts the design system and `PLUMB.md` at the **repository root**, and lists every UI package in `PLUMB.md`
(`UI packages:`) with its stack. Each UI package's global stylesheet becomes a generated copy of the tokens CSS. A
package that has no UI (an API, a worker) is listed as "no UI" and left alone.

If you usually open sessions inside a package (`apps/web`), the tools may not load skills from the root. Init offers a
one-line pointer in that package's `AGENTS.md`/`CLAUDE.md` so agents still find the design system.

### A separate frontend and backend

- **Run init in the frontend repo:** the design system lives there.
- **Run init in a backend-only repo:** Plumb asks "Where will the UI live?" (a) the frontend is in another repo
  (recommended): give the path, Plumb sets it up there and, only if you say yes, writes a small linked `PLUMB.md` in the
  backend repo pointing at it; (b) the frontend will live here; (c) design only for now.

### Several repos share one design system (linked repos)

One repo is the **home** (`Role: home`): it owns the tokens. Every other repo gets only a **linked** `PLUMB.md`:

```
Design system: `../acme-web/.claude/skills/acme-design-system/`
Role: linked
```

plus the "read before you work" row pointing there. Agents in the linked repo read the home's skill; its audit runs
the home's scripts on the linked repo's UI folders. The home's token build can also write generated CSS copies into the
other repos (their paths go in the home's tokens file). To set up a linked repo, run `/plumb:init` there and answer
"Yes, it lives in another repo". Design changes always happen in the home repo.

If the home repo isn't where `PLUMB.md` says, the session starts with
`design system not found` and a `fix:` line: clone or pull the home repo to that path, or correct `Design system:`.

### Opened in the wrong folder

Plumb never assumes the folder you opened is the project:

- **A parent folder** (say `~/Desktop` or `~/Projects`): it lists the projects under it and asks which one. It writes
  nothing in the parent. Open your next sessions in that project's folder: the hooks look for `PLUMB.md` from where a
  session opens.
- **A subfolder** of a repository: it uses the repository root and says so ("you opened apps/web").
- **A folder inside a bigger project** (outside git, with a monorepo or a `PLUMB.md` above): it asks whether the
  project is the folder above.
- **A project that already has Plumb:** init never sets up a second one. It shows status, offers to resume a
  half-finished setup, and offers `/plumb:upgrade` when the plugin is newer.

### Design only (no app yet, a backend repo, or React Native)

Choose **design only** when there's no app to wire into yet. Plumb makes the whole design system and an HTML
prototype, but writes nothing into an app: web styling with plain CSS, no generated copies, starter components as
references inside the skill (`assets/platforms/web/starter/`). `PLUMB.md` records `UI packages: none yet: design only`.
Add real platforms later with `/plumb:update`.

**React Native** themes are not part of 1.0.0 (a candidate for 1.1.0). In a React Native app Plumb offers design only,
web (when the repo has a web part), or native iOS (SwiftUI) / Android (Compose) themes, and never writes React Native
components.

### Moving the design system later

If the design system ended up in the wrong place, never move it by hand. Plumb moves it and updates every reference
(`PLUMB.md`, the `AGENTS.md`/`CLAUDE.md` row, the Makefile) in one step, then checks the generated files:

```
python3 <plugin>/scripts/scaffold.py --relocate .github/skills/acme-design-system .claude/skills/acme-design-system --project-root . --dry-run
python3 <plugin>/scripts/scaffold.py --relocate .github/skills/acme-design-system .claude/skills/acme-design-system --project-root .
```

`/plumb:status` and `/plumb:init` notice when `PLUMB.md` and the real location disagree and offer this move for you.

---

## Every command

| Command | Use it when | What it does |
|---|---|---|
| `/plumb:init` | First time in a project | Finds the right home, routes to create or extract, wires Plumb in |
| `/plumb:create` | A new project | Product interview → design decisions → 2–3 directions → the design system → key screens |
| `/plumb:extract` | A project with UI already | Inventories every value in use → clusters → a clean token set → the same design system and a prototype of every route |
| `/plumb:prototype` | A new screen, tab, flow or interaction, or a visible change to one | 2–3 variants, each clickable and with every state → you pick → it joins the main prototype |
| `/plumb:tour` | A demo, training, onboarding or what's-new walkthrough | Writes a custom walkthrough the prototype plays in guide or play mode, plus a shareable page |
| `/plumb:audit [fix \| improve]` | Any time | Report; `fix` repairs issues with your OK; `improve` makes the screens and the system better |
| `/plumb:ux` | After building a screen or flow | A deep UX review against the prototype, the UX rules and usability heuristics |
| `/plumb:update` | The design changes | Change or add tokens and components, add a platform, apply the audit's system suggestions |
| `/plumb:upgrade` | The plugin has a new version | Brings the project's copied files and settings up to the plugin's version |
| `/plumb:status` | You want a health check | Versions, placement, stale files, audit counts, prototype state, checks, what to do next |
| `/plumb:feedback` | Plumb itself got something wrong, or you want to see what it got wrong | Records Plumb's own mistakes in `~/.plumb/feedback/` (the agent does this itself); typed, reports them grouped and drafts issue text |

### `/plumb:init`

**Use it when** you start using Plumb in a project, or come back to one and want to see where it stands.

**What it asks:** the "Plumb found … I'll create …" block, including the UI files the audit and the checks will cover
(OK, or change the skill's place, the project root, the UI packages, the copy path, the UI files or the docs folder);
whether the design system lives in
another repo (linked); new or existing; then each wire-in item: the `PLUMB.md` values, both checks on or off, the
`AGENTS.md`/`CLAUDE.md` row, the Makefile targets, the Slate review check, Kiro steering, the monorepo package pointer.

**What it changes:** `PLUMB.md`, the design-system skill folder and `docs/design/` (through create or extract), one
row in `AGENTS.md` or `CLAUDE.md`, three Makefile targets (`tokens`, `tokens-check`, `design-audit`), and optionally
one line in `SLATE.md` and `.kiro/steering/plumb.md`. Nothing outside the agreed lines changes. `PLUMB.md` always
names the direct commands; only when you say yes to the Makefile does it add the `(make tokens)` hints
(`scaffold.py --verify` reports a `make` target that `PLUMB.md` names but the Makefile lacks).

**Run again** in a set-up project: it shows status, resumes a half-finished setup from the first missing stage, offers
`/plumb:upgrade` when the plugin is newer, and runs `scaffold.py --verify` to check the placement. It never overwrites a
design system.

```
you   /plumb:init
plumb Plumb found: project ~/Projects/acme … I'll create … OK, or change something?
you   OK
plumb Does this repo use a design system that lives in another repo?  (a) No, this repo owns it (Recommended)
you   a
plumb Extract the system you already have from the code (Recommended: 142 UI files) or create a new one?
you   Extract
      … /plumb:extract runs …
plumb Turn on both checks? (a) Both on (Recommended) (b) edit check only (c) end-of-turn only (d) both off
you   a
plumb Add the Plumb row to AGENTS.md? (Recommended: it exists)
      …
plumb Done. Commit these files, start a new session here so the hooks load. UI work is prototype first.
```

### `/plumb:create`

**Use it when** the project has no UI yet and you want a design system made for it.

**What it asks**, in this order:

- **A. The product first** (up to four questions at once, each with suggestions from your README, briefs and brand
  files): what it is in one sentence; who it is for; where and how often it's used; the 3–5 key tasks; the feel, with
  reference products; your existing brand. Then a five-line summary: "Right?"
- **B. Platforms and stack:** web, iOS (SwiftUI), Android (Compose); the framework and styling it detected (Tailwind
  v4, Tailwind v3, plain CSS; shadcn when present), for you to confirm.
- **C. Design decisions, one at a time**, each recommended from what you said: personality, density, accent, neutrals,
  semantic colours, label colours, type, spacing, radius, elevation, motion and reduced motion (keep fades, or no
  animation at all), icons, dark mode (and, as its own question, how your app switches: the system setting, a `.dark`
  class, both, or a `data-theme` attribute; when your code already uses next-themes with `attribute="class"`, `class`
  is recommended and the question shows the `file:line` it found), accessibility target (WCAG 2.2 AA by default),
  vocabulary and voice, and the UX patterns as seven questions (navigation, page anatomy, forms, feedback,
  empty/loading/error states, destructive actions, onboarding; any it skips, it names and says why). With Tailwind it
  also asks whether to switch off Tailwind's built-in scales so only the tokens exist (all six: colours, radii,
  shadows, text sizes, fonts, easings; recommended for a new app; for an app that already uses classes like
  `bg-emerald-500`, keeping them is recommended, since a reset would leave them colourless). Keeping them keeps the
  default classes working, and the audit still reports defaults that aren't on your scales (`text-lg`, `rounded-xl`) as
  off-scale, as before. The reduced-motion, theme-switch and palette answers are recorded in the tokens file
  (`$extensions.plumb.motion.reduced`, `$extensions.plumb.web.theme_switch`, `$extensions.plumb.web.reset_palette`)
  and the generated CSS follows them.
- **D. Directions:** 2–3 distinct, finished-looking directions on one page, each with a real screen of your product in
  light and dark. Pick one, combine parts, or change something.
- **E. Generate**, with a checkpoint at each step: the full token set; the list of files (the real scaffold runs only
  with the `--confirm` token printed by the dry run you approved); what changes in a
  stylesheet you already have (e.g. `app/globals.css`: Plumb adds a marked `plumb:start … plumb:end` block and owns
  only that; the rest stays yours); when that stylesheet sets its own theme variables (a stock create-next-app sets
  `--color-background`, `--color-foreground`, `--font-sans` and `--font-mono` in an `@theme inline` block, which would
  override the tokens), the token each maps onto and the lines that go, asked once with "move them into the tokens"
  recommended (`build-tokens.py --overrides`, then `--overrides --apply` on your yes); each contrast fix; which
  starter components, in which framework, where. If you choose keep fades for reduced motion in a plain-CSS app, add
  the class `motion-fade` to elements whose transition is only a fade.
- **F. Prototypes** of the key screens (or later, with `/plumb:prototype`).
- **G. Record:** every decision goes in the decision log.

**What it changes:** the design-system skill (`.claude/skills/<project>-design-system/`), `PLUMB.md`, the generated
CSS copy in your app, the starter components (in your app, e.g. `components/ui/`, or as references in the skill when
there is no app), and `docs/design/` (directions, specimen, decision log, prototype).

**Done when** the audit on the components exits 0, `build-tokens.py --check` exits 0, and `docs/design/specimen.html`
shows every token and component in light and dark. Before it says done, the agent walks a final checklist: every
checkpoint asked, the contrast evidence in `dark-mode.md`, the components, the decision log, a first prototype screen
(or your "later"), the wire-in, and `.plumb-tmp/` removed.

```
you   /plumb:create
plumb A1 What are you building, in one sentence? (Recommended) "A booking tool for a small restaurant's hosts" …
      A2 Who is it for? (Recommended) hosts, trained, all evening on a tablet …
      …
plumb C3 Accent colour. (Recommended) #1f7a8c / dark #4fb3c4: calm, readable at night · #b4532a … · #3f51b5 …
      …
plumb I'll write the directions page to docs/design/directions.html. (a) Write it (Recommended) (b) Another path
you   a
plumb Open docs/design/directions.html. Which direction? (a) Quiet service (Recommended: …) (b) … (c) … (d) Combine
you   a, with b's type
plumb The full token set: color.primary #1f7a8c · dark #4fb3c4 … OK?
you   OK
plumb scaffold.py --dry-run would write 32 files: … Write them?
      …
plumb Contrast: on-surface-muted on sunk is 4.1:1 in dark (needs 4.5). Use #9aa5ae (4.6:1)? (Recommended)
      …
plumb Audit on components/ui: 0 errors. Specimen: docs/design/specimen.html. Prototype the key screens now?
```

### `/plumb:extract`

**Use it when** the project already ships UI and you want a design system that matches it.

**What it asks:** which folders hold the UI (and what to leave out); each token group from the before/after page
(accept, rename, merge, split, leave out; after three groups you may accept the rest at once); the product and UX
questions the code can't answer; how the app switches themes, reduced motion and (with Tailwind) whether to keep
Tailwind's built-in scales (keeping them is recommended: the audit then suggests moving those colour classes onto
tokens over time, and still reports off-scale defaults such as `text-lg`); then the same checkpoints as create (token
set, files, your existing stylesheet, your stylesheet's own theme variables with the mapping the agent checked, where
any variable whose colours no token matches is shown with "the look changes" and both values, contrast fixes,
components); which routes to prototype; and, once
you've looked, whether to approve each screen (a screen synced from code is never approved without your yes).

**What it changes:** the same files as create, plus `docs/design/extract.html` (the before/after page) and one screen
file per route in `docs/design/prototype/screens/`. Existing components are mapped into the specs; your app code
changes only with your OK. The final audit reports what doesn't match yet; it does not fix it.

```
you   /plumb:extract
plumb Which folders hold the UI? (Recommended) app/, components/ — leave out vendor/?
you   yes
plumb Found 61 colours in 12 groups, 14 font sizes in 9 groups … I'll write docs/design/extract.html. OK?
      Group "primary": #14857F (212 uses) + #13857e (3) + #158680 (1) → color.primary. Accept? (Recommended)
      …
plumb Routes found: / → home, /bookings → bookings, /bookings/[id] → booking … Prototype all of them? (Recommended)
      …
plumb Audit: 37 errors, 12 warnings in 88 files (report: docs/design/audit-2026-10-12.html).
      Fix them now with /plumb:audit fix, or create Slate tickets by area? (Slate only when the project uses it)
```

### `/plumb:prototype`

**Use it when** you are about to add or change a screen, tab, flow or interaction: a new page, a new step in a flow, a
changed layout, a new dialog. Also when the edit check says a screen has no approved prototype, or the end-of-turn check
says code changed without its prototype. (Small fixes that change neither what a screen shows nor how it behaves, such
as a logic bug, a typo or data wiring, need no prototype step.)

**What it asks:** what the screen is for, which key task, which states matter; one updated version or 2–3 variants;
before writing the variants' files (and where); which variant you choose (or what to combine or change); before writing
the chosen screen into the main prototype; whether you approve each new or changed screen; before recording the
decision; then whether to build it now, make a Slate ticket, or leave it for later.

**What it changes:** `docs/design/prototype/proposals/<name>/` (the variants, both views and the app view each, plus
`index.html`), `docs/design/prototype/screens/<id>.html` (the chosen screen), a default walkthrough in
`docs/design/prototype/tours/<flow>.json`, the rebuilt `prototype.html`, `app.html` and `screens.html`, your approval in
`screens.json`, and a decision entry. A component the screen needs that doesn't exist yet is listed as "to build" in
`references/inventory.md`.

```
you   /plumb:prototype billing
plumb What is billing for? (Recommended) "See what a client owes and send a reminder" (key task 3)
      Which states matter? loading · empty (no invoices) · error · overdue · long names …
plumb One version or 2–3 variants? (Recommended: variants, it's a new screen)
plumb I'll write the variants in docs/design/prototype/proposals/billing/ (a-calm-list, b-dense-table, c-by-client)
      and build both views of each. OK?
you   OK
plumb Open docs/design/prototype/proposals/billing/index.html. Which variant? (Recommended) B: hosts compare amounts…
you   B, with A's empty state
plumb I'll write screens/billing.html, link it from home.html, and add tours/billing.json. OK?
      …
plumb Review: prototype.html#screen-billing · Demo: app.html#/billing · every state: screens.html
plumb Approve billing as the reference to build?
you   Approve
plumb billing is approved: build it to match docs/design/prototype.html#screen-billing. Build it now, a Slate ticket, or later?
```

### `/plumb:tour`

**Use it when** you want a walkthrough beyond the default one `/plumb:prototype` writes for each flow: a client demo,
training with hands-on "your turn" steps, onboarding a teammate, a design review, or a "what's new" tour, across one
flow or several.

**What it asks:** who is watching (client, training, review, team, what's new; this sets the tone and whether it
opens in play or guide mode); what they should take away; which flows, screens and states; when it matters, pacing,
chapters, the intro and closing cards and which steps are "your turn". Then it shows the steps as a table and asks
before writing.

**What it changes:** `docs/design/prototype/tours/<id>.json`, and the generated `prototype.html` and
`docs/design/tours/<id>.html` (the shareable page). If a step needs an element the screen file lacks, it asks before
adding it (which makes that screen's approval stale until you approve it again).

```
you   /plumb:tour client-demo
plumb Who is watching? (a) a client or stakeholder demo, opens in play mode (Recommended) (b) training …
plumb In one sentence, what should they take away?
you   "A booking takes under a minute"
plumb Steps:  1 Tonight at a glance · home · spotlight .tables · "The host lands on tonight's tables…" …
      Write this tour to docs/design/prototype/tours/client-demo.json?
you   Write it
plumb Open docs/design/prototype.html#tour-client-demo, or send docs/design/tours/client-demo.html (works offline).
```

### `/plumb:audit`

**Use it when** you want to know whether the UI follows the design system: any time, before a release, after a big
change, or when Slate's review runs `make design-audit`.

It runs `audit.py` (every rule, contrast in light and dark, drift of generated files, prototype fidelity), takes
screenshots of built screens beside their prototype screens when a browser is available, and then the agent reviews
what no rule can express: hierarchy broken while still using tokens, two screens solving one thing differently, words
off the vocabulary, an unhelpful empty or error state, something that looks wrong in dark mode. Those findings are
marked **agent review** in the report, separate from rule findings, and never change the exit code. When the agent keeps
finding the same kind of problem, it proposes it as a new rule.

**Output:** `docs/design/audit-YYYY-MM-DD.html` (issues ranked by severity, each with `file:line`, what's wrong and the
fix; then an **Improvements** section), a terminal summary, and an exit code: 0 no errors, 1 errors, 2 nothing checked
or bad input. Exit 1 is a result, not a crash, though your agent tool may show it as a failed command. Severities: **error** fails the audit and the edit check refuses edits that add one; **warn** is reported;
**suggest** is an improvement that never fails anything.

**What it asks:** your dev server's URL, when built screens need screenshots (it never probes `localhost` itself;
"not running" skips them); after the summary, one question: `/plumb:audit fix`, `/plumb:audit improve`, Slate tickets
(only when the project uses Slate), or nothing now.

**Three modes:**

- **`/plumb:audit`** reports only.
- **`/plumb:audit fix`** repairs errors and warnings with your OK. It groups them by what fixes them ("12 raw colours →
  colour tokens", "3 screens drifted from the prototype"), shows each group with a before → after example, and asks:
  Apply, Show every change first, or Skip. Then it re-runs until clean. A value with no close token is never invented:
  it is collected for `/plumb:update`. Anything that changes how a screen looks goes through its screen file and your
  approval first.
- **`/plumb:audit improve`** is for a project that already passes. It builds a ranked improvement plan from the
  report's Improvements, the agent review and a design pass across the product (hierarchy, spacing rhythm, consistency
  between screens, states, dark-mode polish, accessibility beyond AA), including **the design system itself** (a
  missing or mergeable token, a component that needs a variant, a rule screens keep breaking for a good reason). You
  pick items: screen changes go prototype first, then build; system changes go through `/plumb:update`; any item can
  be a Slate ticket instead.

**Without a design system yet** (a prototype file, or code before `/plumb:extract`), the audit runs in
**inconsistency-only** mode: it infers the de-facto scales from the code and flags near-duplicates and one-off values.

```
you   /plumb:audit
plumb audit: 3 errors, 2 warnings in 58 files checked
      errors: raw-colour ×2 (components/cards/summary-card.tsx:14 …), screen-drift ×1 (detail)
      improvements: 4 (missing-token "surface-raised", 3 uses …)
      Report: docs/design/audit-2026-10-12.html
      Next? (a) /plumb:audit fix (Recommended) (b) Slate tickets (c) nothing now
you   /plumb:audit fix
plumb Group 1: 2 raw colours → colour tokens. bg-[#1f7a8c] → bg-primary. Apply this group?
```

### `/plumb:ux`

**Use it when** a screen or flow is built and you want it reviewed as a user meets it, or you want a polish pass.

It compares the built screen with its approved prototype screen, then checks it against your `ux.md` rules, nine
usability heuristics (visibility of status, match with the real world, user control, consistency, error prevention,
recovery, recognition over recall, minimal design, help), accessibility beyond contrast (keyboard path, focus order,
labels, target sizes, reduced motion) and a visual polish pass (hierarchy, spacing rhythm, alignment, type details such
as tabular numbers and line length, density, how motion feels). With a browser it takes screenshots at phone and
desktop widths in light and dark, side by side with the prototype; without one it reviews the code.

**What it asks:** which screen or flow (when unclear); the URL of your dev server, once, to see the built screen; then
fix now, Slate tickets, or nothing now.

**What it changes:** writes `docs/design/ux-review-YYYY-MM-DD.html` and its screenshots. Fixes happen only after you
pick them, prototype first for anything visible.

```
you   /plumb:ux booking
plumb Is the app running? Dev server URL? (e.g. http://localhost:3000)
you   http://localhost:3000
plumb Reviewed booking at 390 and 1280 px, light and dark, beside its prototype.
      2 errors (no visible focus on "Book the table"; error state missing in code), 3 warnings, 4 suggestions.
      Report: docs/design/ux-review-2026-10-12.html. Fix now, Slate tickets, or nothing now?
```

### `/plumb:update`

**Use it when** the design itself changes: a colour, a type size, a new token, a new component or variant, adding iOS
or Android to a web-only system, improving a part (motion, dark mode, density), or applying the audit's suggestions for
the system.

**What it asks:** what changes (or, recommended when there is a recent audit, "apply the latest audit's system
suggestions", proposed one at a time with the evidence); then each change as **before → after, in light and in dark**
(for example `color.primary: #1f7a8c → #1a6f80 (light) · #4fb3c4 → #5cc0d1 (dark)`); renaming or removing a token
lists every use first; the matching `design.md` lines; and the decision entry.

**What it changes:** only the tokens file for values, the specs for components, then it regenerates every theme, copy,
the specimen, the prototype pages and the token block of every old proposal (so old variants still render). It records
the decision, runs the audit and shows the diff.

**Adding a platform** needs the project to be on the plugin's version: if it is older, update asks you to run
`/plumb:upgrade` first. It then adds that platform's themes, references and starter components, each shown and asked;
the scaffold runs for real only with the `--confirm` token from the dry run you approved.

```
you   /plumb:update add iOS
plumb Platforms: web → web, ios. scaffold.py --dry-run would write: references/mobile/README.md, …/ios/ios.md, …
      (your files: skip, kept). OK?
      …
plumb build-tokens.py wrote assets/platforms/mobile/ios/AcmeTheme.swift … Contrast: all pairs pass in light and dark.
      Decision DS-20261012-add-ios recorded. Audit: 0 errors. git diff --stat: …
```

### `/plumb:upgrade`

**Use it when** the plugin has a newer version than the project (the session-start line says
`run /plumb:upgrade`), or after you update the plugin.

**What it does, in order:** compares `PLUMB.md`'s version with the plugin's; shows **What's new** for every version in
between and asks before changing anything; replaces Plumb's own files in the project (the scripts and templates; it
shows the dry run's list inside the question and runs it only with the `--confirm` token that dry run printed);
migrates the tokens file by **adding** new settings only (it never deletes or changes a value;
a tokens file without the theme-switch and reduced-motion settings gets the defaults the build already used, `both`
and `none`, so the build's "not set" note stops; `build-tokens.py --migrate` does the same on its own);
regenerates every generated file; runs each version's upgrade steps in order, asking before each ("Keep as is" is the
default); updates `PLUMB.md` (version line, any new setting, a dated line under "Plumb updates"); runs the checks until
healthy; shows the diff. You commit.

**What it never does:** touch your components, delete your values, run by itself, or commit.

- **Project newer than the plugin** (a teammate upgraded first): it never downgrades. It prints the commands to update
  your plugin and asks you to run them.
- **Linked repo:** only the `PLUMB.md` version line changes; the design system is upgraded in the home repo.
- **Something went wrong:** it restores only Plumb's own files, one path at a time, from what the dry run listed, and
  asks before deleting anything new.

```
you   /plumb:upgrade
plumb This project is on Plumb 1.0.0; the plugin is 1.1.0.
      What's new in 1.1.0: …
      Upgrade from 1.0.0 to 1.1.0 now?
you   yes
plumb Replace Plumb's files as listed? (scripts/*.py, templates/*, assets/platforms/README.md)
      …
plumb Step 1 (…): needed. Run it?  Keep as is (default) / Run it
      …
plumb Now on Plumb 1.1.0. Checks: up to date, audit 0 errors. Commit it, e.g. "Plumb: upgrade to v1.1.0".
```

### `/plumb:status`

**Use it when** you want a quick health check, at the start of UI work, or to see what is left to build.

It is **read-only** (the one exception: if the design system sits in the wrong place and you say yes, it runs the
move). It reports: project and plugin versions; the system's path, home or linked, platforms, styling, themes; whether
`PLUMB.md` and the real location agree; stale generated files; audit errors, warnings and suggestions; the prototype
(screens built and to build, approvals pending, screens synced from code to confirm, drift, routes not prototyped,
tours, whether the pages are stale); the checks on or off; whether the Effective HTML skills are available or Plumb's
built-in quality bar is in use; uncommitted design files; and the one most useful next step. In a set-up project the
next step is never "create" or "extract" (it's an approval, a screen to build, `/plumb:prototype`, `/plumb:audit fix`
or `improve`, `/plumb:update` or `/plumb:upgrade`); a missing `Routes:` line or a leftover
`.plumb-tmp/setup-in-progress` marker points you to `/plumb:init`. Status writes no file, not even a temporary one.

```
you   /plumb:status
plumb Version: project 1.0.0 · plugin 1.0.0
      System: .claude/skills/acme-design-system/ (home) · web · tailwind-v4 · light and dark
      Generated files: up to date · Audit: 0 errors · 2 warnings · 5 suggestions (last report 2026-10-12)
      Prototype: 9 screens (7 built, 2 to build: /billing, /settings) · 1 approval pending (billing)
      Checks: edit check on · end-of-turn check on · prototype sync on
      Next: approve the billing screen.
```

### `/plumb:feedback`

**Use it when** Plumb itself got something wrong: a script's result the agent had to correct, a hook that refused
the wrong thing (or missed something, or crashed), a skill step that was unclear, wrong or missing, a template or doc
that disagrees with the code, a quirk of one CLI. Or when you want to see everything Plumb got wrong on this machine.

**Plumb mistakes only.** The test: *would fixing this mean changing Plumb, not the project?* A detection that proposed
`src/**` for a monorepo whose UI lives in `frontend/src/` is a Plumb mistake (feedback). A hard-coded `#123456` in your
page is your project's design issue (`/plumb:audit`); a design choice goes in the decision log; your app's own bugs go
in your tracker.

It has two modes:

- **Log** (the agent, by itself). Every Plumb skill says: "When a Plumb script or hook is wrong and you correct it,
  record the Plumb mistake with /plumb:feedback." The agent writes one Markdown file per mistake,
  `~/.plumb/feedback/YYYY-MM-DD-<script>-<category>-<project>.md`, with its normal file-write tool (your CLI's
  permission mode decides whether it asks; Plumb adds no question), says so in one line and carries on. You can also
  type `/plumb:feedback log <what went wrong>`.
- **Report** (you type `/plumb:feedback`). It reads every record (all your projects) and the hooks' own `hooks.md`,
  groups them by script · function · category with counts and projects, most frequent first, shows given vs expected,
  then asks, one question at a time: show a group in full, draft a GitHub issue for Plumb (text only, never sent), mark
  a group handled, or filter by project, script or date.

A record (every field; "unknown" rather than a guess):

```markdown
# detect.py — missed structure

- **When:** 2026-10-13 · Plumb 1.0.0 · Claude Code · macOS 15
- **Project shape:** monorepo, UI in frontend/ (Next.js · Tailwind v4), backend in api/
- **Where it failed:** scripts/detect.py → the UI-file patterns
- **Command:** `python3 <plugin>/scripts/detect.py --cwd . --json` (cwd: the repo root)
- **Given:** `"ui_files": ["src/**"]`
- **Expected:** `frontend/src/**`: the UI package is frontend/
- **Evidence:** `src/**` matched 0 files; `frontend/src/**` matches 48 (frontend/src/app/page.tsx:1 …)
- **Repro:** a repo with frontend/package.json (next) and frontend/src/app/page.tsx; run detect.py at the root
- **Category:** missed structure
- **Suggested fix in Plumb:** detect.py writes the UI patterns relative to the root, with the package folder
- **Handled here:** UI files corrected to `frontend/src/**` inside the placement question, recorded in PLUMB.md
```

A crash adds the exit code and the last lines of the traceback; a hook mistake adds the event, tool, path, exit code
and its exact message. The categories: missed structure, wrong guess, false positive, missed problem, crash, timeout,
confusing message, skill gap, docs mismatch, CLI quirk. A record holds paths, `file:line`, the repo's shape and short exact
text: never your source code, never a secret. In Kiro the command is `/plumb-feedback`. More:
[Plumb's own mistakes: the feedback log](#plumbs-own-mistakes-the-feedback-log).

---

## The daily loop: prototype first

Every UI change that adds or changes a screen, tab, flow or interaction follows one order:

```
 /plumb:prototype <screen> ─▶ you pick a variant ─▶ you approve the screen ─▶ the agent builds it to match
        ─▶ the hooks keep every edit on the system ─▶ /plumb:audit (and /plumb:ux) ─▶ commit
```

1. **Ask for the screen first.** "Prototype a billing page" → `/plumb:prototype billing`. Compare the variants, every
   state, in light and dark. Approve one.
2. **Build it to match.** The agent reads the approved screen file (`docs/design/prototype/screens/billing.html`) and
   the design-system skill, then writes the real code with tokens only.
3. **The hooks hold it true while it builds:**
   - a new page or route with no approved screen is refused (`fix: /plumb:prototype billing`);
   - an edit that adds a raw colour, an off-scale size or another design-system error is refused, with the token to use;
   - at the end of the turn, the files changed in this session are checked, including whether a built screen changed
     without its prototype.
4. **Map it.** Once the route exists, the screen is linked to its route and source files
   (`build-prototype.py --map billing --route=/billing --files "app/billing/**"`), so the audit can compare them.
5. **Check and commit.** `/plumb:audit` (or `make design-audit`) exits 0; `/plumb:ux billing` for a deeper look.

**Changing an existing screen** works the same way: the agent updates the screen file first, you approve it, then the
code follows. If code changed first (a quick fix that turned out visible), the end-of-turn check stops the agent once
and asks it to update the screen file; you approve it, or mark it "synced from code" to confirm later.

**Small fixes** that change neither what a screen shows nor how it behaves (a logic bug, a typo, data wiring) need no
prototype step.

---

## Prototypes, the screens catalogue, variants and approval

Every Plumb project has **one main prototype of the whole product**, kept in step with the real frontend:

- **`docs/design/prototype.html`**: the clickable app. Every screen, its navigation and interactions (links, tabs,
  dialogs, menus, form validation, toasts), with a state switcher, a phone/desktop toggle, a light/dark toggle, a
  "Why it looks like this" panel per screen (the decisions behind it, who made them, the options considered), a guide
  panel per screen, a Decisions page, and the walkthrough player.
- **`docs/design/app.html`**: the app view, for a demo. Every screen full window, with none of the prototype's
  panels (no screens list, state switcher, toggles, decisions or player): it looks and clicks like the product. The
  screens' own links, buttons and theme toggle work; the theme follows your system until a screen's toggle picks one,
  and the browser remembers it. A sidebar marked `data-app-sidebar` stays in view while a long page scrolls, and a
  dialog a click opens is scrolled into view. **prototype.html to review, app.html to demo.**
- **`docs/design/screens.html`**: the catalogue. A sidebar, and every screen in every state (loading, empty, error,
  success, disabled, long text, zero, offline where relevant) in **light and dark side by side**, plus every control
  state (default, hover, focus, pressed, disabled, loading).

Every page opens from disk, with no server and no network.

**One source per screen.** Every page is built by `build-prototype.py` from
`docs/design/prototype/screens/<id>.html`: one file per screen, its states marked with `data-state`, its interactions
inline, and only the design system's tokens for colours, type, spacing, radius, shadow and motion. Edit a screen file
and rebuild; every page follows, so they can never disagree. The audit runs on the screen files like on your code.

**Links you can share:** `prototype.html#screen-booking` opens a screen; `#screen-booking/error` a screen in one state;
`#tour-client-demo` a walkthrough; `#tour-client-demo-3` its step 3. In the app view: `app.html#/booking` and
`app.html#/booking/error` (the `#screen-…` links work there too); `app.html` alone opens the first screen (the lowest
`data-order`).

**The map, `screens.json`.** `build-prototype.py` is its only writer. For each screen it records the route, the source
files that build it, the states, its status (`to-build` until every source glob matches a file, then `built`) and your
approval:

| Command | What it records |
|---|---|
| `build-prototype.py --map billing --route=/billing --files "app/billing/**"` | the route and source files, confirmed with you |
| `build-prototype.py --approve billing` | your approval: who (git `user.name`, else `$USER` / `%USERNAME%`), when, and a hash of the screen file. Editing the screen file afterwards makes the approval stale |
| `build-prototype.py --synced billing` | the screen file was updated to match code that was already built; listed for you to confirm, never blocking |
| `build-prototype.py --check` | nothing written; exit 1 when a page (`app.html` included) or token block is stale or missing, exit 2 when a walkthrough step points at something that no longer exists |

**Variants.** `/plumb:prototype` makes 2–3 variants that differ in UX (layout, flow, density, navigation), all on the
same design system. Each comes as **both views**, its clickable prototype and its every-state catalogue, so you compare
how loading, empty and error look, not only the happy path, plus its app view for a demo:

```
docs/design/prototype/proposals/billing/
  a-calm-list/screens/billing.html     the variant's screen file (what goes to main if chosen)
  a-calm-list/idea.md                  its idea and trade-offs
  a-calm-list/prototype.html           clickable, to review (generated)
  a-calm-list/app.html                 full window, to demo (generated)
  a-calm-list/screens.html             every state, light and dark (generated)
  b-dense-table/…
  index.html                           the variants side by side: "Review: prototype.html · Demo: app.html" (generated)
```

The chosen variant's screen file is copied into the main prototype; the others stay in `proposals/` as the record. When
tokens change, their token block is refreshed so old variants keep rendering.

**Always in step, both ways.** A screen "to build" stays listed in `/plumb:status` and the audit until its route
exists. When a screen's source files change and its screen file doesn't, the end-of-turn check stops the agent once and
the audit reports `screen-drift`. A route with no screen is `route-not-prototyped`.

**Figma?** For screens, flows, states and handoff, the prototype replaces it: real HTML on real tokens, audited,
clickable, and kept in step with the code. Figma stays better for freehand visual exploration, designers editing
together on one canvas, and handoff to teams that don't build with agents.

---

## Tours: guide mode and play mode

Every `prototype.html` has a **walkthrough player**. A walkthrough's script is a tour file,
`docs/design/prototype/tours/<id>.json`: which steps, which words. `/plumb:prototype` writes a default one for every
flow it builds; `/plumb:tour` writes custom ones. The prototype stays fully clickable with or without them.

**Two modes from one file:**

- **Guide mode:** step by step with Next and Back (or the arrow keys; Esc leaves), a spotlight and a coach mark on each
  step's element. For a reviewer, a new teammate, a learner.
- **Play mode:** plays the flow like a video: actions run by themselves, captions narrate, a progress bar has a marker
  per chapter you can jump to, Space pauses and resumes, and the speed is 0.5×, 1×, 1.5× or 2×. With reduced motion it
  still plays by itself and only drops the cursor glide and animation.

The audience picks the mode that opens first: a client demo and "what's new" open in play mode; training, review and
team tours in guide mode. The other mode is one click away.

**Adding text:** a caption (the subtitle line), a callout bubble on a chosen side of an element, numbered or named
labels on several elements at once, a note placed anywhere, title cards (intro, chapter, closing), and text typed into a
real field letter by letter in play mode.

**Pointing:** spotlight (dims the rest), ring (outline, rest visible), arrow with a short label, beacon (a pulsing dot;
static with reduced motion), zoom, and a cursor that moves and clicks in play mode. One step can point at several
elements.

**"Your turn" steps** teach: in guide mode the tour waits until the learner does the action on the real control (a wrong
click shows a hint); in play mode the same step runs by itself. One tour is both the demo and the hands-on lesson.

**Pacing:** chapters (named groups of steps, shown as scene markers), intro and closing cards ("what you'll see",
"what to try next"), a default speed, and a longer hold on a step that needs reading.

**Sharing:** every tour is also its own page, `docs/design/tours/<id>.html`: the whole prototype plus that tour, opening
straight into it. It opens from disk with no network, so you can email it to a client or put it in training material;
viewers can leave the tour and click around.

**Tours stay in step:** every element a step points at must exist in the screen file. When a screen changes so that a
step no longer matches, `build-prototype.py` exits 2 naming the tour, the step and the fix, and the pages aren't rebuilt
until it's fixed. Recording approvals still works meanwhile. `/plumb:tour <id>` fixes a custom tour.

Captions and callouts are announced to screen readers, and every control works by keyboard. Turning a tour into
in-app onboarding in the live product is not part of 1.0.0.

---

## The design-system files and who owns them

Every file has an owner, and the owner decides who may change it and what an upgrade touches:

- **[Y] yours:** written at create or extract from your answers, changed through `/plumb:update` (or by you).
- **[G] generated** from the tokens or the screen files: never edited by hand (the guard hook refuses it); rebuilt.
- **[P] Plumb's:** the scripts and templates copied into the project; `/plumb:upgrade` replaces them; never hand-edited.
- **[A] agent-written** in your framework: your components; upgrades never touch them.

```
.claude/skills/<project>-design-system/
├── SKILL.md                              [Y] when to use it, the files, the workflow (prototype first), hard rules
├── design.md                             [Y] the look in words; wins every disagreement; revision notes
├── assets/
│   ├── tokens/<project>.tokens.json      [Y] THE one source of every value (W3C design tokens), light and dark
│   ├── icons/icon-map.json               [Y] concept → Lucide / SF Symbol / Material Symbol
│   └── platforms/
│       ├── README.md                     [P] what is generated and how to regenerate it
│       ├── web/tokens.css.template       [Y] the CSS structure for your styling mode
│       ├── web/tokens.css                [G] + an exact copy at your app's path (e.g. app/globals.css)
│       ├── web/tailwind.tokens.js        [G] Tailwind v3 only
│       ├── mobile/ios/<Project>Theme.swift         [G] when iOS is a platform
│       ├── mobile/android/<Project>Theme.kt        [G] when Android is a platform
│       └── */starter/                    [A] starter components, only while no app exists
├── references/
│   ├── components.md · inventory.md · ux.md · accessibility.md · motion.md · vocabulary.md   [Y]
│   ├── dark-mode.md                      [Y] + a [G] block: the computed contrast of every colour pair
│   ├── fidelity.md                       [Y] when a prototype or brand guide existed before Plumb
│   ├── web/  stack.md · components.md · ux-guidelines.md · dark-mode.md                       [Y]
│   └── mobile/  README.md · components.md · ios/ · android/                                   [Y]
├── scripts/                              [P] build-tokens.py · audit.py · build-prototype.py · _plumb.py
└── templates/                            [P] the specimen, report, prototype shell, app shell and player templates
docs/design/
├── decisions.md                          [Y] the design decision log
├── directions.html · extract.html            the create directions / the extract before-and-after (the record)
├── specimen.html                         [G] every token and component, light and dark
├── prototype.html · app.html · screens.html  [G] the main prototype, the app view and the catalogue
├── prototype/screens/<id>.html           [Y] one source per screen
├── prototype/screens.json                [G] the map (build-prototype.py only)
├── prototype/tours/<id>.json             [Y] walkthrough scripts
├── tours/<id>.html                       [G] one shareable page per tour
├── prototype/proposals/<name>/           variants: screen files and idea.md [Y], pages [G]
└── audit-*.html · ux-review-*.html           reports
PLUMB.md                                  [Y] Plumb's settings for this project
```

**One token source.** Values live only in `<project>.tokens.json`: light values in `$value`, dark values in
`$extensions.plumb.dark`, references like `{color.primary}`. Every theme, copy, specimen and prototype token block is
generated from it. To change a value, change the token (`/plumb:update`), then rebuild.

**Contrast is computed, never guessed.** `build-tokens.py` measures every pair in light and dark (WCAG 2.2: 4.5:1 for
text, 3:1 for large text and UI boundaries) and writes the evidence table into `references/dark-mode.md`. A failing pair
is an audit error whose fix names the nearest passing value; Plumb never changes a colour without your OK.

**Light and dark, everywhere.** Every colour token has a dark value; a missing one is an audit error unless the token is
marked `"same-in-dark": true`. Pages never write `dark:` overrides: the tokens switch. A light-only project is an
explicit decision, recorded in the decision log and in `PLUMB.md` (`Themes: light-only`).

### `PLUMB.md`

At the project root, written by init, read by every command and every hook (simple `Key: value` lines), safe to edit:

```
<!-- plumb v1.0.0 · written by /plumb:init, safe to edit values -->
# Plumb: the design system for Acme

Design system: `.claude/skills/acme-design-system/`
Role: home                          (home = this repo owns the tokens; linked = uses another repo's)
Platforms: web
UI packages: . (Next.js · Tailwind v4 · shadcn)
Python: `python3`
No downloads: nothing is installed or downloaded; if something is missing, ask the user and wait for their decision.

## Checks
Edit check: on
End-of-turn check: on
Themes: light-and-dark          (light-and-dark | light-only: an explicit decision)
UI files: app/**, components/** · *.tsx *.jsx *.css
Allowed raw values: components/ui/**

## Commands
tokens `python3 .claude/skills/acme-design-system/scripts/build-tokens.py` (make tokens)
check `python3 .claude/skills/acme-design-system/scripts/build-tokens.py --check` (make tokens-check) · audit `python3 .claude/skills/acme-design-system/scripts/audit.py` (make design-audit)

## Prototype
Main: docs/design/prototype.html · app: docs/design/app.html · screens: docs/design/screens.html · map: docs/design/prototype/screens.json
Prototype sync: on               (end-of-turn check stops once when a built screen changed without its prototype)

## Plumb updates
- 2026-10-12 created with Plumb 1.0.0 (web; direction "Quiet service")
```

The `(make …)` hints in `## Commands` appear only when you said yes to the Makefile targets; without them the lines
are the direct commands.

| Setting | What it does |
|---|---|
| `Design system:` | Where the skill is (in a linked repo, the path into the home repo) |
| `Role:` | `home` (this repo owns the tokens) or `linked` (uses another repo's) |
| `Python:` | The command every skill, the Makefile and the fix lines use (`python3`, `python`, `py -3`) |
| `Edit check:` | `on`: an edit that adds design-system errors is refused |
| `End-of-turn check:` | `on`: the files changed in a session are checked when the agent finishes its turn |
| `Prototype sync:` | `on`: a new page with no approved screen is refused, and code that changed without its screen stops the agent once |
| `Themes:` | `light-and-dark`, or `light-only` (turns off the dark rules; a recorded decision) |
| `UI files:` | Which files the audit and hooks treat as UI |
| `Allowed raw values:` | Paths where primitives live (e.g. `components/ui/**`): raw values are allowed there. Exceptions are by path only, never by a comment in the code |

### Commands you can run yourself

From the project root (with the `Python:` command from `PLUMB.md`):

```
make tokens          # python3 <skill>/scripts/build-tokens.py           write every theme from the tokens
make tokens-check    # python3 <skill>/scripts/build-tokens.py --check   exit 1 when a generated file is stale
make design-audit    # python3 <skill>/scripts/audit.py                  the audit; exit 0 = no errors
python3 <skill>/scripts/audit.py --html                                  the audit with its HTML report
python3 <skill>/scripts/build-prototype.py                               rebuild the prototype pages
python3 <skill>/scripts/build-prototype.py --check                       exit 1 when a prototype page is stale
```

Every flag of every script, with "use it when", is in the plugin's
[reference/scripts.md](../plugins/plumb/reference/scripts.md). Put `make tokens-check` and `make design-audit` in your
CI to keep everyone honest.

---

## Hooks: what they check, what they say, how to switch them

Three hooks run in Claude Code and Copilot CLI (and Kiro, pending its live check). They do nothing in a folder without
`PLUMB.md`. They run **only the plugin's own installed scripts**, never the copies inside your project, so a cloned
repository can't get code run just by containing a `PLUMB.md` (see `SECURITY.md`, "Trust boundary"). They **fail open**:
no Python, a broken file or unreadable input never blocks your work (at most one note).

### At session start

One status line, so the agent knows the project has a design system:

```
Plumb: acme-design-system 1.0.0 · tokens up to date · 1 audit issue · read the skill before UI changes
```

Possible extras: `Plumb 1.1.0 is installed; this project's design system is 1.0.0: run /plumb:upgrade` (the project is
older than the plugin); `this project's Plumb scripts are v1.0.0; the plugin is v1.1.0 — run /plumb:upgrade` (the
copied scripts differ); `design system not found` with a `warning:` and a `fix:` line (the path in `PLUMB.md` is
missing; the checks are off until it is fixed). It also takes a snapshot of the UI files already changed, so the
end-of-turn check only looks at what this session changed. The audit count is capped at 2 seconds; set the
`PLUMB_AUDIT_TIMEOUT` environment variable (seconds, `0` skips it) to change that. Last comes one short pointer,
`Plumb mistakes (a Plumb script, hook or skill got it wrong) → /plumb:feedback`, so the agent knows where Plumb's own
mistakes go even in a project with no `AGENTS.md` or `CLAUDE.md`.

### Before each edit (and shell write)

Three checks, in this order:

1. **The guard (always on):** hand edits to generated files and to Plumb's own files are refused, including through the
   shell (`>`, `tee`, `sed -i`, `cp`, `Set-Content`, …). Removing or moving away a guarded file (`rm`, `rmdir`, `del`,
   `Remove-Item`, `git rm`, `mv` / `Move-Item` / `git mv` from it), or a folder holding one, is refused the same way.
   Running `build-tokens.py` or `build-prototype.py` is allowed.

   ```
   error: app/globals.css is generated from the design tokens; a hand edit is lost on the next build
   fix: change the tokens with /plumb:update, then rebuild: python3 .claude/skills/acme-design-system/scripts/build-tokens.py
   ```
   ```
   error: docs/design/prototype.html is generated by build-prototype.py from the screen files; a hand edit is lost on the next build
   fix: edit the screen files in docs/design/prototype/screens/ (or the tours in docs/design/prototype/tours/), then rebuild: …
   ```
   ```
   error: .claude/skills/acme-design-system/scripts/audit.py is Plumb's file; upgrades replace it
   fix: use /plumb:update for design changes, or propose the improvement to the Plumb repo
   ```

2. **Prototype first** (`Prototype sync: on`): creating a page or route that no approved screen covers is refused.

   ```
   error: app/reports/page.tsx is a new screen with no approved prototype
   fix: /plumb:prototype reports (design the screen, get the user's approval, then build it to match)
   ```

   When a screen exists but isn't approved yet, the message ends with `ask the user: approve screen reports in …? Then
   record it: … --approve reports`.

3. **The edit check** (`Edit check: on`): the file before and after the edit is audited, and **only the errors the edit
   adds** are refused (older code never blocks you), at most 10 at a time:

   ```
   Plumb edit check: this edit adds 3 design-system errors to components/cards/summary-card.tsx
   error: line 2: raw colour #3b6fd4
   fix: no colour token is close (nearest color.outline-input = #6b7686, ΔE 14.4): add a token with /plumb:update, then use it
   error: line 2: arbitrary design value text-[15px]
   fix: text-body (typography.body = 16px); if the design needs 15px, add a token with /plumb:update, then use it
   error: line 2: arbitrary design value rounded-[18px]
   fix: rounded-lg (radius.lg = 12px); if the design needs 18px, add a token with /plumb:update, then use it
   ```

   Layout geometry (`w-[320px]`, `top-[…]`, grid templates) is always allowed, and so are raw values on the
   `Allowed raw values:` paths.

### At the end of the agent's turn

The **end-of-turn check** (`End-of-turn check: on`): when no UI file changed in the session, it stays silent. Otherwise
it audits the changed files, including prototype sync (a built screen whose code changed while its screen file didn't).
New errors stop the agent **once**, with the list and fixes:

```
Plumb end-of-turn check: 1 new design-system error in the files changed this session. Fix them now, or tell the user why not (this check stops you once):
error: components/cards/summary-card.tsx line 2: raw colour #3b6fd4
fix: …
```

The agent fixes them (or tells you why not) and finishes; the check never loops. A clean turn prints one line:
`Plumb: 2 UI files checked, consistent`.

### Switching them

In `PLUMB.md`: `Edit check: on|off`, `End-of-turn check: on|off`, `Prototype sync: on|off`. They are read on every
run, so a change applies at once. The guard has no switch (in a project with `PLUMB.md`); to stop it everywhere, disable
the plugin.

### In Copilot CLI and Kiro

- **Copilot CLI** hides a hook's error output, so refusals come back as a "deny" answer with the same `error:` and
  `fix:` text; the agent sees the reason. Session start uses Copilot's context field. Edits arrive as patch text and are
  checked the same way. The end-of-turn check makes Copilot keep working: its answer arrives as a new prompt, so the
  skills tell the agent to report and stop when you had said not to fix now. On Windows, Copilot runs each hook's
  PowerShell command (through `hooks/run.cmd`).
- **Copilot CLI asks before every script.** It ignores the skills' pre-approved commands (`allowed-tools`), so expect
  a permission prompt per script run and per file the agent writes: for a whole `/plumb:init` with create or extract,
  about 10–15 script prompts (the skills run each checkpoint's scripts in one shell call) plus one per file written
  (often 15–25); `/plumb:status` asks once. Temporary files stay inside the project (`.plumb-tmp/`, ignored by version
  control). A permission prompt is never your answer to a Plumb checkpoint: the question comes first. To cut the
  prompts, answer "remember for this session", start Copilot with `--add-dir <plugin folder>` (no path prompts for
  the plugin's scripts), or with `--allow-tool 'shell(python3)'` (every `python3` command, not only Plumb's: your call;
  Copilot has no setting that pre-allows only Plumb's scripts). Details: `plugins/plumb/reference/copilot.md`.
- **Kiro:** the same three scripts, each run with `--kiro` from `.kiro/hooks/plumb.json`: session start prints the
  status line; the edit check runs on Kiro's `write` and `shell` tools and refuses with exit 2 and the `error:` and
  `fix:` (or `ask the user:`) lines; the end-of-turn check answers `{"decision": "block", "reason": …}`. Kiro's docs
  show that JSON for CLI v3; whether it makes the agent continue is part of the pending live check. On Windows each
  hook starts through PowerShell, which adds about 0.3 s per hook. Plumb's own `.kiro/hooks/plumb.json` and
  `.kiro/skills/plumb-*/` are guarded too: hand edits to them, shell writes and removals (`rm`, `mv`, `Remove-Item`,
  …) are refused, in the project and in your home folder (`~`, `$HOME` and `%USERPROFILE%` paths included). Change
  the checks in `PLUMB.md` and refresh with `kiro.py install`.

---

## Plumb's own mistakes: the feedback log

Plumb's scripts are a first guess, and the agent corrects them (scripts give evidence, not answers). Each time it
corrects one, it records the **Plumb mistake** so Plumb's developers can fix it for everyone: that is the feedback
log. It holds Plumb mistakes only; your project's design issues are `/plumb:audit` findings.

**Where it lives:** `~/.plumb/feedback/` (`%USERPROFILE%\.plumb\feedback\` on Windows), plain Markdown, outside every
project, never committed, never sent anywhere.

- `YYYY-MM-DD-<script>-<category>-<project>.md`: one file per Plumb mistake the agent corrected (`/plumb:feedback`
  above has the format).
- `hooks.md`: the hooks write their own failures here, one line each, when one fails open (a crash, a plugin script
  it cannot load, a script that timed out): the hook, the Plumb version, the CLI, the OS, the project folder's name, the
  event, tool and path, the exit code, and `Given: … · Expected: …`. The same failure is written once a day; the file
  stops growing at 512 KB; a timeout (a slow repo) is written once per project and Plumb version. The message is
  redacted: quoted literals become `'<redacted>'`, absolute paths outside the project keep only their base name, and
  token-like strings and secret values become `<redacted>`. It is private: `~/.plumb` and `feedback/` are kept 0700
  (your own folders with wider permissions are tightened, e.g. after a umask of 002) and `hooks.md` is 0600; nothing
  is written through a symlink or into someone else's folder (see `SECURITY.md`). A problem with the log never blocks or fails a hook. Your
  project's own broken files (a tokens file that is not JSON) are not Plumb mistakes and are not logged.
- `handled.md`: the index `/plumb:feedback` keeps when you mark a group handled (`handled in <version>`).

### How to read findings

- **Type `/plumb:feedback`.** The report groups everything by script · function · category, most frequent first, with
  the projects, dates, versions and CLIs, and shows given vs expected for each group; then it asks what to do next,
  one question at a time. A drafted issue names projects only by their shape and is never sent: post it yourself on
  the Plumb repository if you want to.
- **Or open the folder.** The records are plain Markdown: `open ~/.plumb/feedback` (macOS), `xdg-open ~/.plumb/feedback`
  (Linux), `explorer %USERPROFILE%\.plumb\feedback` (Windows), or any editor. `hooks.md` is one line per failure.

**For Plumb's developers**, the flow for one group:

1. **A minimal repro**: the record's Repro line, as the smallest folder that shows it.
2. **A failing test** in the Plumb repository (a fixture under `tests/fixtures/` and a test next to the script's
   others), red before the fix.
3. **The fix** in the plugin's script, hook, skill or doc.
4. **A patch release** (1.0.x; see `AGENTS.md`, "Releasing a version"), so projects get it through `/plumb:upgrade`.
5. **Mark the group handled** in `/plumb:feedback` with that version. A group seen again on that version or later shows
   up as "came back".

## Teams and enterprises

### The decision log

Every design choice (a direction, a variant, a screen, a token change, light-only) goes in
`docs/design/decisions.md`, one entry each:

```
## DS-20261012-billing-layout · Billing as a dense table
- Date: 2026-10-12
- Decided by: Sam Lee
- Options: calm list, dense table, by client ([variants](prototype/proposals/billing/index.html))
- Chosen: dense table
- Why: hosts compare amounts side by side.
- Screens: billing
- Ticket: ACME-014
```

Entries are append-only and their ids can't collide, so several teams can add decisions on separate branches without
merge conflicts. "Decided by" comes from git's `user.name`. Each screen in the prototype shows its decisions in a "Why it
looks like this" panel, so anyone changing a screen sees what was decided and by whom. When the project keeps a
`docs/decisions.md`, each entry is mirrored there too.

### No downloads

Plumb never installs or downloads anything: no package, font, icon set, image, browser or tool. Its scripts are Python
standard library only. If a component really seems to need a new package, the agent says so (`ask the user: …`) and
waits for your decision. The rule is in the `AGENTS.md`/`CLAUDE.md` row Plumb adds and in `PLUMB.md`, so every agent
in the project sees it. (Enforcing it on other tools is outside Plumb; an install guard can do that.)

### Offline pages

Every page Plumb generates (prototype, screens, tours, specimen, reports, directions) loads nothing from the network:
no CDN, no hosted web fonts, no remote images. A project font is used from the project's own font files; otherwise a
system font stack. Every page opens from disk, offline, on any machine.

### Screenshots without installing anything

Most checks need no browser: the audit reads code, CSS and prototype HTML directly. The visual extras (screenshot
comparison in `/plumb:audit` and `/plumb:ux`) use the first browser available, installing nothing: the agent's own
browser tool if your organisation allows one; else a Chrome, Edge or Chromium already on the machine, run headless by
`screenshot.py`; else the visual part is skipped with a note and every other check still runs.

### Slate

When the project uses Slate (`kanban/board.py` exists), Plumb offers, each asked:

- `make design-audit` in `SLATE.md`'s review checks, so every Slate review runs the audit;
- audit and UX findings as tickets, grouped by area, written only through `board.py`;
- a ticket that adds or changes a screen starts with "prototype approved" and links the screen in the main prototype in
  "done when".

Plumb never edits `kanban/`; Slate never edits the design system.

### Effective HTML (optional)

The [Effective HTML](https://github.com/plannotator/effective-html) skills (`html`, `design-artifact`,
`html-prototype`, `html-diagram`) are **optional, used when installed, with Plumb's built-in quality bar otherwise**.
When they are in the session, Plumb follows them for the pages an agent writes: the create directions, the prototype
variants and screen files, the extract before/after page and the UX review page. When they are not, it follows its own
rules ("The quality bar" in [reference/prototypes.md](../plugins/plumb/reference/prototypes.md): real content, every
state, working interactions, keyboard and focus, both themes, reduced motion, no generic look) and its directions
template. The specimen, the audit report and the prototype shell are Plumb's own fixed templates either way.

**Your design system outranks Effective HTML.** In a project, Effective HTML is followed for craft only (real content,
states, interactions, accessibility, polish); the palette, type, spacing, radius and motion always come from your
`<project>-design-system`, and where the two disagree, your system wins. The one exception is create's directions
page, written before any system exists: each direction there is a candidate system.

`/plumb:init` tells you once whether the skills are available, and `/plumb:status` reports it.

Plumb never installs them. To add them, run these yourself in Claude Code (from Effective HTML's README):

```
/plugin marketplace add plannotator/effective-html
/plugin install plannotator-effective-html@effective-html
```

Copilot CLI and other agents: see [Effective HTML's README](https://github.com/plannotator/effective-html#install)
for how to install it there.

### Operating systems, SSH and tmux

macOS, Linux and Windows are all supported and tested in CI (Python 3.9 and 3.13 on each). On Windows, install Python
from python.org or the Microsoft Store; Plumb tries `py -3`, `python` and `python3`, and records the one that works in
`PLUMB.md`'s `Python:` line. Everything is plain text in a terminal, so it works over SSH and in tmux; open the HTML pages
from disk on whichever machine holds the files.

### Controlling the plugin

- Plumb is one Git repository with no build step: mirror or fork it, review it, and install from your internal copy
  (`claude plugin marketplace add <your mirror>`, or `claude --plugin-dir <path>`).
- Releases are tagged `vX.Y.Z` with notes from the changelog; pin the version you approved.
- `/plumb:upgrade` never runs by itself, and each project's upgrade is a diff you review and commit.
- Test tools (pytest, Playwright) are used only in Plumb's own CI, never in your project.
- Security reports: privately through GitHub (see `SECURITY.md`).

---

## Troubleshooting

The messages below are what Plumb really prints. Every `error:` line comes with a `fix:` line: do what it says.

**The agent says nothing about Plumb at session start.**
The hooks look for `PLUMB.md` from the folder the session opened in, upwards. Open the session in the project folder
(not a parent folder), and start a new session after `/plumb:init` so the hooks load. In Claude Code, check the plugin
is enabled (`/plugin`); in Copilot CLI, restart after installing.

**The agent asks me to confirm a block, list or summary I can't see.**
Plumb's skills put what you confirm inside the question itself; text printed just before a question can be hidden in
Claude Code. Answer "show it" (or choose "change something"), and the agent asks again with the content inside.

**The end-of-turn check never stops the agent.**
Check for a leftover `.plumb-tmp/setup-in-progress` file in the project: the check stands down while it exists (it
marks a setup in progress), for at most 6 hours; after that session start says the marker is stale and the check runs
again. `/plumb:init` treats it as a half-finished setup and offers to resume; if you don't need
it, delete the `.plumb-tmp/` folder.

**The prototype-first check never refuses a new page, or the audit never reports `route-not-prototyped`.**
`PLUMB.md` has no `Routes:` line, or its `UI files:` patterns match nothing (a monorepo package such as `frontend/`
needs `frontend/src/**`, not `src/**`). The session-start line then says `Routes not recorded — run /plumb:init to
record them`; a project set up on an early 1.0.0 build has no `Routes:` line yet. Run `/plumb:init` (or
`/plumb:update`) to record them, as `<path> (<kind>)`; `scaffold.py --verify` reports both.

**`error: the scaffold writes into the project only after the user approved the dry-run list`** (or
**`--confirm … does not fit this command`**)
The real scaffold needs the token its dry run printed, and the token goes stale when an answer, an argument or a file
changes in between. The agent runs the dry run again, shows you the list, and uses the new token after your OK.

**`Plumb: … · design system not found · read the skill before UI changes`**
`PLUMB.md` names a design-system folder that isn't there. In a linked repo, clone or pull the home repository to that
path, or correct `Design system:`. In a home repo, correct the path or run `/plumb:init`; if the skill was moved, use
`/plumb:status`, which offers the `--relocate` that puts everything back in step.

**`error: app/reports/page.tsx is a new screen with no approved prototype`**
Prototype first: run the `fix:` command (`/plumb:prototype reports`), approve the screen, then build it. If the screen
exists but isn't approved, the message asks you to approve it. If this page really needs no screen (an internal debug
route), map it to an existing screen or set `Prototype sync: off` in `PLUMB.md` as a team decision.

**`error: … is generated from the design tokens; a hand edit is lost on the next build`**
You (or the agent) tried to edit a generated theme or copy. Change the token instead (`/plumb:update`), then run the
`fix:` command to rebuild.

**`error: … is generated by build-prototype.py from the screen files`**
Edit `docs/design/prototype/screens/<id>.html` (or a tour file) and rebuild; never the generated page.

**`error: … is Plumb's file; upgrades replace it`**
The scripts and templates in your design-system skill belong to Plumb. A design change goes through `/plumb:update`; a
better script goes to the Plumb repository as an issue or pull request, and reaches projects through `/plumb:upgrade`.

**`Plumb edit check: this edit adds 3 design-system errors …`**
Use the token each `fix:` names. When it says `no colour token is close`, the design needs a value the system doesn't
have yet: add a token with `/plumb:update`, then use it. Never invent a value in code.

**`Plumb end-of-turn check: … (this check stops you once)`**
The agent changed files with new errors, or a built screen without its prototype. It should fix them now or tell you
why not; it won't be stopped again for the same findings.

**`stale: …` and `fix: python3 …/build-tokens.py` from `make tokens-check`**
A generated file is out of date: run `make tokens` (the `fix:` command). The build is deterministic, so running it again
changes nothing. When it's up to date you see `ok: 4 generated files are up to date`.

**`error: several tokens files in …` or `error: no tokens file in …`**
The skill's `assets/tokens/` must hold exactly one `*.tokens.json`. Keep one; for none, run `/plumb:create` or
`/plumb:extract`.

**A tokens file error such as `error: acme.tokens.json: invalid JSON at line 12, column 5`**
Open the file at that line and correct it (no trailing commas, no comments). Errors always name the token or line.

**`error: no screen files in docs/design/prototype/screens/`** from `build-prototype.py`
There is no prototype yet: `fix: write the first screen with /plumb:prototype <screen>`.

**`build-prototype.py` exits 2 naming a tour, a step and a selector**
A screen changed and a walkthrough step no longer matches it. Update the step (or run `/plumb:tour <id>`), then rebuild.
Approvals still work meanwhile.

**`note: visual comparison skipped: no browser found`**
No browser tool and no Chrome, Edge or Chromium was found. Plumb installs nothing; every other check still ran. If a
browser is installed somewhere unusual, pass its path with `--browser PATH`.

**The audit reports `no-prototype`**
`Prototype sync` is on but there are no screen files yet. Run `/plumb:extract` (existing app) or
`/plumb:prototype <screen>`, or set `Prototype sync: off` if the project has no prototype by decision.

**`error: … nothing was checked` (exit 2) from the audit**
The paths you gave hold no UI files of the types Plumb reads (`.tsx .jsx .ts .js .vue .svelte .astro .html .css
.scss .swift .kt`). Check the paths and `UI files:` in `PLUMB.md`.

**Copilot CLI: `✗ skill(plumb:init) Skill not found: plumb:init` right after `/plumb:init`**
Harmless. Typing the command already loaded the skill; the model then also tried Copilot's skill tool, which lists only
skills an agent may start on its own (init, create, extract, update and upgrade run only when you type them). The flow
goes on.

**`problem: PLUMB.md names … but there is no Makefile`** (or `… but the Makefile has no … target`) from `scaffold.py --verify`
`PLUMB.md` sends people to a `make` target that doesn't exist (the Makefile was removed or edited). Add the targets
again (`templates/Makefile.snippet`, or `/plumb:init`), or drop each `(make …)` hint from `PLUMB.md`'s `## Commands`
lines: the direct commands there work without make.

**Windows: nothing happens, or `python` is not found**
Install Python 3.9+ (python.org or the Microsoft Store). The hooks try `py -3`, `python`, then `python3`, and never block
your work when none is found. Put the command that works in `PLUMB.md`'s `Python:` line.

**`Plumb 1.1.0 is installed; this project's design system is 1.0.0: run /plumb:upgrade`**
Run `/plumb:upgrade` when you're ready; nothing breaks meanwhile (the hooks check with the plugin's own scripts).

**The project is newer than my plugin**
A teammate upgraded first. Update your plugin (`claude plugin marketplace update plumb`, then
`claude plugin update plumb@plumb`, then `/reload-plugins`). Plumb never downgrades a project.

---

**The hooks never write `~/.plumb/feedback/hooks.md`, even after a crash note.**
The log is private: if `~/.plumb` or `~/.plumb/feedback` is a symlink or someone else's folder, the hooks write
nothing there (your own folders with wider permissions are made 0700 instead). Remove the link, or make the folders
yours, and the next failure is logged. A full log (512 KB) is left alone too: move the old `hooks.md` aside. A
project's own broken file (a tokens file that is not JSON) is not a Plumb mistake and is never logged.

## FAQ

**Do I need Figma?** Not for screens, flows, states and handoff: the prototype is real HTML on your real tokens,
audited and kept in step with the code. Figma remains better for freehand exploration and designers editing together.

**Can I edit the tokens file by hand?** Yes, it's yours. Keep the format (light in `$value`, dark in
`$extensions.plumb.dark`), then run `make tokens` and `make design-audit`. `/plumb:update` does the same with checks and a
decision entry, so it's the recommended way.

**Can I edit the generated CSS?** No: the guard refuses it and the next build would overwrite it. Change the token or the
template (`assets/platforms/web/tokens.css.template` is yours), then rebuild.

**Where do my components go?** Into your app, in your framework (e.g. `components/ui/`, built on shadcn/Radix in React,
native controls in SwiftUI and Compose), written by the agent from `references/components.md`. Plumb ships no component
library. With no app yet they wait in the skill as starters.

**Can I mark one line as an exception?** No: exceptions are by path only (`Allowed raw values:` in `PLUMB.md`), never by
a comment, so they're visible and reviewed.

**Can I turn the checks off?** Yes, in `PLUMB.md` (`Edit check`, `End-of-turn check`, `Prototype sync`). The audit
still reports everything when you run it.

**Does it work without git?** Yes, with fewer details. Decision entries written by `/plumb:create` ask for your name
instead of reading git's `user.name`; screen approvals (`build-prototype.py --approve`) record your login name instead
(`$USER`, or `%USERNAME%` on Windows), without asking; and the session snapshot uses file modification times.

**Does it change my app without asking?** No. Every write is shown and asked first; the audit reports and `fix` applies
only the groups you say yes to.

**Does it push, merge or commit?** No. It shows `git status` or `git diff --stat`, and you commit.

**What happens to old prototype variants when tokens change?** Their token block is refreshed so they still render; their
screen files are never touched. They are the record, not kept in step with code.

**Can one design system serve web, iOS and Android?** Yes: one tokens file generates the web CSS (Tailwind v4, v3 or
plain CSS), a SwiftUI theme and a Compose Material 3 theme. Add platforms later with `/plumb:update`.

**What if Effective HTML isn't installed?** Nothing breaks. It is optional and used when installed; otherwise Plumb
follows its built-in quality bar and its own templates, and every page still opens offline in light and dark.
`/plumb:status` says which one is in use. See [Effective HTML (optional)](#effective-html-optional).

**What about React Native or Flutter?** Not in 1.0.0. React Native is a candidate for 1.1.0.

**Does Plumb send anything anywhere?** No. It makes no network calls at run time, and its pages load nothing from the
network.

**Is Kiro supported?** Built from Kiro's documented formats and tested in CI with Kiro-shaped input; the live check on a
real Kiro is pending. See [Kiro](#kiro-built-from-kiros-docs-live-check-pending).

**Where is every command's every flag?** In the plugin's [reference/](../plugins/plumb/reference/) folder, starting
with [scripts.md](../plugins/plumb/reference/scripts.md) and [rules.md](../plugins/plumb/reference/rules.md) (every audit
rule and how to fix it).
