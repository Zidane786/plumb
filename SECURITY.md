# Security policy

Please report security problems **privately** through GitHub:
**Security → Report a vulnerability** on https://github.com/Zidane786/plumb
(private vulnerability reporting is enabled). Don't open a public issue for security bugs.

Useful areas to look at: the hooks (`plugins/plumb/hooks/`), which read tool input and can block
edits, and the scripts Plumb copies into projects (the token generator and the audit), which read
and write files in the project.

You'll get an answer as soon as possible; fixes are released as a new plugin version with a
CHANGELOG entry.
