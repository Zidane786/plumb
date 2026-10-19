#!/bin/sh
# Plumb hook launcher.  Usage: run.sh <script.py> [args...]
#   (hooks.json: run.sh session_start.py, run.sh pre_edit.py, run.sh stop_check.py)
#
# Runs <script.py> (relative to this hooks folder unless absolute) with the first of
# python3, python, "py -3" that is Python 3.9 or newer. stdin and the arguments pass through
# unchanged. If no suitable Python is found it prints one line to stderr and exits 0: a
# missing Python must never block the user's tool calls.
# Uses only shell builtins, so it works with a minimal PATH (Linux, macOS, Git Bash on Windows).

if [ $# -lt 1 ]; then
  echo "plumb: run.sh needs a script name; hook skipped" >&2
  exit 0
fi

script=$1
shift

# This script's folder; $0 may use / or (on Windows) \ as separator.
a=${0%/*}; [ "$a" = "$0" ] && a=
b=${0%\\*}; [ "$b" = "$0" ] && b=
if [ ${#a} -ge ${#b} ]; then here=$a; else here=$b; fi
[ -n "$here" ] || here=.
here=$(cd "$here" 2>/dev/null && pwd) || here=.

case $script in
  /* | [A-Za-z]:[\\/]*) ;;
  *) script="$here/$script" ;;
esac

# True when "$@" is a Python >= 3.9. stdin is /dev/null so the hook's JSON input is kept.
plumb_py_ok() {
  "$@" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' </dev/null >/dev/null 2>&1
}

# PLUMB_PYTHON tells the hook how the user starts Python, for the commands it prints.
if plumb_py_ok python3; then
  PLUMB_PYTHON=python3; export PLUMB_PYTHON
  exec python3 "$script" "$@"
fi
if plumb_py_ok python; then
  PLUMB_PYTHON=python; export PLUMB_PYTHON
  exec python "$script" "$@"
fi
if plumb_py_ok py -3; then
  PLUMB_PYTHON="py -3"; export PLUMB_PYTHON
  exec py -3 "$script" "$@"
fi

echo "plumb: no Python 3.9+ found (tried python3, python, py -3); Plumb hook skipped" >&2
exit 0
