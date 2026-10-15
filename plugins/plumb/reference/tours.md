# Walkthroughs: tour files, guide mode and play mode

Three things, kept apart:

- **the screens** (`/plumb:prototype`, [prototypes.md](prototypes.md));
- **the walkthrough player**, built into every `prototype.html` and every tour page by `build-prototype.py` (guide
  mode and play mode);
- **a tour file** (`<docs>/prototype/tours/<id>.json`): which steps, which words. `/plumb:prototype` writes a default
  one for every flow it builds and updates it when the flow changes; `/plumb:tour` writes extra or custom ones.

The prototype stays fully clickable with or without tours. `<docs>` is the docs folder (default `docs/design`).

## The two modes

- **Guide mode:** step by step with Next and Back (arrow keys; Esc leaves), a spotlight and a coach mark on each step's
  element. For a reviewer, a new teammate, a learner.
- **Play mode:** plays the flow like a video for a client or a demo: actions run by themselves, captions narrate, a
  progress bar has a marker per chapter you can jump to, Space pauses and resumes, restart, speed 0.5×, 1×, 1.5×, 2×.
  With reduced motion it still plays by itself; only the cursor glide and animation are dropped.

The `audience` picks the mode that opens first: `client` and `whats-new` open in play mode; `training`, `review` and
`team` in guide mode. Either mode is one click away. Links: `prototype.html#tour-<id>` opens a tour,
`#tour-<id>-<n>` its step n. Captions and callouts are `aria-live`; every control works by keyboard; a skip link leads
to the walkthrough.

## Where it plays

Each tour file says where its own page, `<docs>/tours/<id>.html`, plays it (`"view"`):

- **`app`** (the default, also when `view` is left out): the full-window app view (the same screens as `app.html`, no
  screens list, no state switcher, no decisions) with the player on top. For a demo, a client, training. The closing
  card offers "Open the prototype" (the same screen in `prototype.html`).
- **`prototype`**: the prototype page, with the screens list and the "Why it looks like this" / decisions rail (they
  fold away while the tour runs and come back when it ends). For a design review.

`prototype.html#tour-<id>` plays every tour in the prototype whatever its view, and `app.html` itself carries no player
(a clean demo). `/plumb:tour` asks "Where should it play?" and records the answer; `/plumb:prototype`'s default tours
leave `view` out (the app view). In both views `#tour-<id>` and `#tour-<id>-<n>` work, and the player moves between
screens (and through the clicks it makes) without adding browser history entries: the tour's place is in the address
(`#tour-<id>-<n>`), so Back leaves the page.

**In the app view the page scrolls**, not a frame, so the player treats what the screen keeps at the top of the window
as part of the window's edge: a step's element is brought into view below the screen's own fixed or sticky headers,
bars and banners (only those across the element's columns, sticking to the window, and less than half the window tall;
a sticky one only when its section reaches the element; several stacked bars add up), never under them. A **zoom** step there scales the page's frame, which would pull the
screen's fixed layers (a fixed header, a toast, a dialog) to the top of the page while it lasts; so on a screen showing
a fixed layer the app view points with a spotlight instead of zooming. In `prototype.html` (and a prototype-view page)
the frame holds those layers, so zoom works as always.

## The player on the page

- **Hide panel** (the button at the top of the walkthrough's panel, or the `H` key) moves the panel out of the way of
  the screen. A small pill stays at the bottom of the window: in guide mode it names the step, in play mode it is only
  the "Show panel" button (the subtitle keeps narrating). `H` again, or the pill's button, brings the panel back. The
  arrow keys, Space and Esc still work while it is hidden. On a "your turn" step the pill also offers "Do it for me";
  a wrong click brings the panel back for that step, with the hint shown and announced; at the end of play the panel
  comes back with "Play again" (and no Hide panel until you play again or leave). Neither changes your choice: the
  next step hides it again. `H` does nothing while you
  type in a field (also a `role=textbox`, `combobox`, `searchbox` or `spinbutton` widget), with Shift, Ctrl, Alt or Cmd
  held, or as a held key repeats. The choice is remembered in this browser (`localStorage`; with storage off it lasts
  for the page).
- **On top, always:** the screen frame is its own stacking context, so a screen's own dialogs, toasts and sheets
  (whatever their `z-index`) stay under the panel, the subtitle, the cursor and the labels. In `prototype.html` the
  frame is also the containing block for what a screen fixes in place (scrims, dialogs, toasts), so they sit inside the
  frame, as on a device of that width, and never cover the toolbar or the screens list.
- **What it points at:** the first element of a selector that is visible: an element hidden with `visibility: hidden`
  (also inside a hidden parent) or pushed off the frame (an off-canvas drawer) is skipped. One that an inner scroller
  has scrolled away (a wide table's far column, a lower item of a fixed-height list) still counts: when the step
  opens, its first element is scrolled into view inside that scroller, once. One a box that does not scroll keeps out
  of view (a carousel's other slide, a collapsed accordion) is passed over for the next match. Nothing else scrolls:
  other elements and labels that a scroller holds out of view are left out, the marks follow your own scrolling inside
  the screen, and a redraw never undoes it. A
  `display: contents` element is pointed at through its first child that has a box.
- **Long pages:** a step scrolls its element into the room between the top bar and the panel, at once (whatever
  `scroll-behavior` the page sets). For an element taller than that room, its top edge and its topmost label come into
  view together when they fit, else the topmost label; with no labels it scrolls only when none of it is in view.
  Title cards stay pinned in the window.
- **Room for the screen:** while a tour runs, the screens list and the "Why it looks like this" / Guide rail fold away,
  so the frame keeps the width the screens' desktop layout needs (their `@container plumb-frame (min-width: 48rem)`
  rules); they come back when the tour ends.
- **The project's look:** the player's colours, fonts, radius and shadow come from the project's tokens where they exist
  (`color.primary` for its accent, `color.surface`, `color.outline`, `font.sans`, `radius.lg`, `shadow.popover` …) and
  fall back to Plumb's neutral look. Subtitles, the play badge and the cursor keep one fixed high-contrast look.

## The file

One tour per file, `<docs>/prototype/tours/<id>.json`; `<id>` is letters, digits, `_` and `-` (and not
`<another tour>-<n>`, which reads as a step link).

```json
{
  "title": "Taking a booking",
  "audience": "client",
  "view": "app",
  "purpose": "Show the owner how a host takes a booking in under a minute.",
  "speed": 1,
  "intro":   {"title": "Taking a booking", "text": "What you'll see: tonight's tables, a booking, the confirmation.", "hold": 600},
  "chapters": [
    {"title": "Tonight at a glance", "steps": [
      {"screen": "home", "state": "ready", "title": "Tonight's tables",
       "caption": "The host lands on tonight's tables, in time order.",
       "target": ".tables", "point": "spotlight",
       "labels": [{"target": "h2", "text": "1 Today"}, {"target": "[data-test=new-booking]", "text": "2 New booking"}]},
      {"screen": "home", "title": "Start a booking", "caption": "One link starts a new booking.",
       "target": "[data-test=new-booking]", "point": {"style": "arrow", "label": "Start here"},
       "callout": {"text": "Every booking starts here", "side": "bottom"},
       "action": {"click": "[data-test=new-booking]"}}
    ]},
    {"title": "Take the booking", "steps": [
      {"screen": "booking", "title": "Type the guest's name", "caption": "The name is the only field to fill in.",
       "target": "[data-test=guest]", "point": "ring", "action": {"type": "Zoë Brontë"}},
      {"screen": "booking", "title": "Book the table", "caption": "Your turn: book the table.",
       "target": "[data-test=save]", "point": "cursor", "action": {"click": true},
       "your_turn": true, "hint": "Not that one: press “Book the table”, the highlighted button."},
      {"screen": "booking", "state": "success", "title": "Booked", "caption": "Confirmed on the same page.",
       "target": ".banner", "point": "beacon", "note": {"text": "Saved in one step", "x": 62, "y": 18}}
    ]}
  ],
  "closing": {"title": "What to try next", "text": "Take a booking yourself, or try the error state.", "hold": 600}
}
```

| Field | Meaning |
|---|---|
| `title` | The tour's name (shown in the player and the tour page). |
| `audience` | `client`, `training`, `review` (default), `team` or `whats-new`: sets the caption tone and the opening mode. |
| `view` | Where its page `tours/<id>.html` plays it: `app` (default: the full-window app with the player on top) or `prototype` (the prototype page with the screens list and the decisions rail, for a design review). Anything else exits 2 naming the file and line. See "Where it plays". |
| `purpose` | One sentence: why this tour exists (shown on the intro). |
| `speed` | Default play speed: `0.5`, `1`, `1.5` or `2`. |
| `intro`, `closing` | Title cards: `{"title", "text", "hold"}` ("what you'll see", "what to try next"). |
| `chapters` | Named groups of steps, shown as scene markers: `{"title", "text", "hold", "steps": [...]}`. Or a flat `steps` list instead. |
| `hold` | Milliseconds to stay on a card, chapter title or step (longer for a step that needs reading), at most 60000. |

**A step:**

| Field | Meaning |
|---|---|
| `screen` | The screen id (its file name in `prototype/screens/`). |
| `state` | One of that screen's `data-state` names (default: its first). |
| `title`, `caption` | The coach-mark title and the subtitle / narration line. Use the project's vocabulary and the audience's tone. |
| `target` or `targets` | One CSS selector, or several (several rings or labels in one step). |
| `point` | How to point at the target: `spotlight` (dims the rest), `ring` (outline, rest visible), `arrow`, `beacon` (a pulsing dot; static with reduced motion), `zoom` (enlarges the area and outlines it; an area that already fills the view is only outlined), `cursor` (moves and clicks in play mode), `none`; or `{"style": "arrow", "label": "Start here"}`. |
| `callout` | A bubble attached to the target: `{"text", "side": "top" \| "right" \| "bottom" \| "left"}`. |
| `labels` | Numbered or named tags on several elements: `[{"target", "text"}]`. |
| `note` | Text placed anywhere: `{"text", "x", "y"}` (percent of the screen). |
| `action` | What happens: `{"click": SELECTOR}` or `{"click": true}` (the target), `{"type": TEXT, "target"?}` (typed letter by letter in play mode), `{"choose": VALUE, "target"?}` (a select or radio), `{"wait": MS}`. |
| `your_turn` | Teaching: in guide mode the tour waits until the learner performs the action on the real control (a wrong click shows `hint`); play mode performs it by itself. One tour is both the demo and the hands-on lesson. |
| `hint` | What to say after a wrong try on a `your_turn` step. |
| `hold` | As above. |

## Targets must exist in the screen file

Every selector a step uses (`target`, `targets`, `labels[].target`, `action` targets) must match an element **in the
screen file's markup**, in that step's state or the screen's shared content. The element may be hidden (a
`hidden` error message that appears after a wrong submit is a fine target); it may not be something a script creates at
run time, because the check reads the file, not the running page. Prefer stable hooks: `[data-test=save]`, a class,
an element type inside the section; avoid deep positional chains.

`build-prototype.py` checks every tour against the screens with a standard-library CSS subset (type, `#id`, `.class`,
`[attr op value i]`, descendant, `>`, `+`, `~`, `:first-child`, `:last-child`, `:only-child`, `:nth-child()`,
`:nth-of-type()`, `:not()`, `:is()`, `:checked`, `:disabled`, `:required`). A bad field, an unknown screen or state, a
selector that matches nothing, or one the check cannot read exits 2 naming the tour file, the line and the fix.

**When a tour breaks** (a screen changed, an element was renamed): the build and `--check` exit 2 until the tour is fixed
(update the step's selector or state, or the screen file). `--map`, `--approve` and `--synced` still write
`screens.json`, warn about the tour and exit 0, so recording an approval never waits on a tour. Fix the tour in the same
change that broke it: `/plumb:prototype` updates the default tour of the flow it changes; `/plumb:tour <id>` rewrites a
custom one.

## Checking a tour

Two passes, both evidence for the agent, never a substitute for looking ([scripts.md](scripts.md)):

1. **Static, every machine:** `build-prototype.py --check-tour <docs>/prototype/tours/<id>.json` checks the one file as the
   build does and writes nothing (exit 0 / 2). It also warns when a step's element sits in something the screen's own
   CSS hides at some frame widths (`display: none`, `visibility: hidden` or an off-canvas `transform` undone inside an
   `@container plumb-frame (min-width: …)` rule, or the reverse): `… visible only when the frame is ≥ 48rem`. That
   matters where the frame is narrower than the window: the prototype page (screens list and rails, and its phone
   frame); in the app view the frame is the window. Fix by pointing the step at an element shown at every width, or by
   playing the tour in the app view.
2. **In a browser, when one is on the machine:** the plugin's `check-tour.py <docs>/tours/<id>.html` plays the tour page
   headless in guide and play mode at 1280 and 1440 wide and checks, per step: the right screen and state; every target,
   label and action element laid out, not `visibility: hidden` or `opacity: 0`, not zero-size, inside the window and
   not covered by the panel or the screen's own fixed or sticky bar;
   the dock not covered by the screen. Problems come one line per step, e.g. `step 12 (Users › Invite): the target
   ".invite" is hidden (visibility: hidden) at 1280 (guide, play)`, exit 2. No browser: exit 3 with a note; Plumb
   never installs one, so say so and ask the user whether to continue without it. Exit 1 (the browser gave no result): ask whether to try another
   installed browser (`--browser`) or continue without it.

## Every tour is also its own page

`build-prototype.py` writes `<docs>/tours/<id>.html` for each tour: one self-contained file with every screen (tokens,
interactions) and that tour, opening straight into it (play mode for a client or what's-new audience, guide mode
otherwise), in the tour's view: the full-window app (default) or the prototype page. It opens from disk with no server and no network, so it can be emailed or put in training
material; viewers can leave the tour and click around. It is generated: never edit it, it is rebuilt whenever a screen
or the tour changes, and `--check` fails when it is stale. A tour page whose tour file was removed is deleted.

Turning a tour into in-app onboarding in the live product is not part of Plumb 1.0.0.

## Writing good tours

- **Default tour per flow** (`/plumb:prototype`): the happy path of the flow, one step per meaningful screen or action,
  plus one step on the most important non-happy state (the error or empty state); `audience: "review"`, no `view`
  (it plays in the app view).
- **Custom tours** (`/plumb:tour`): ask who is watching and what they should take away; pick the screens and states
  across one flow or several; chapters per part of the story; an intro ("what you'll see") and a closing card ("what to
  try next"); `your_turn` steps for training; a longer `hold` where there is something to read.
- Captions say what the person does and why it matters, in the product's words (`vocabulary.md`), one sentence each.
- Keep annotations few per step: one pointer plus at most a callout or a set of labels.
