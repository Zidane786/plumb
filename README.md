# Plumb

**Plumb keeps a project's design true.** It is a plugin for Claude Code and GitHub Copilot CLI
that creates, extracts, audits and maintains a project's design system, so every screen Claude
builds uses the same colours, type, spacing, components and words.

- **New project:** Plumb asks what you're building and who it's for, walks you through the design
  decisions one at a time, shows 2–3 directions to pick from, and writes a design-system skill
  into the project: one token file that generates the web, iOS and Android themes, plus component
  specs, accessibility and dark-mode rules, and an audit.
- **Existing project:** Plumb reads the UI you already have, lists every colour, size and
  component actually used, merges near-duplicates, and builds the same skill from what's there.
- **While Claude builds:** hooks stop edits that bypass the design system and check the changed
  screens before Claude hands back.

Plumb is in design. The first release (0.1.0) will add the install steps, the commands and a
full example of what a project gets. See [Releases](https://github.com/Zidane786/plumb/releases).

## License

[MIT](LICENSE)
