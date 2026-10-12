# Plumb

Create, extract, prototype, audit and maintain a project's design system, so every screen an agent
builds stays consistent. Works with Claude Code and GitHub Copilot CLI.

## Install

```
/plugin install plumb --marketplace Zidane786/plumb
```

The full guide is written in a later step of the 1.0.0 build.

## Hooks

Three hooks run in both tools: a status line at session start, a check before each edit, and an
end-of-turn check. They run only the plugin's own scripts, never the copies in a project (see
SECURITY.md, "Trust boundary"). In GitHub Copilot CLI, whether the end-of-turn check can make the
agent continue (Copilot's `agentStop`) is decided by the live test; until then the check before
each edit is the hard guard there.
