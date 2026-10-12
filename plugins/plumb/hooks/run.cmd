@echo off
rem Plumb hook launcher for Windows (GitHub Copilot CLI runs hooks through PowerShell there).
rem   hooks.json: powershell -> run.cmd session_start.py, run.cmd pre_edit.py, run.cmd stop_check.py
rem Same job as run.sh: runs <script.py> from this hooks folder with the first of py -3, python,
rem python3 that is Python 3.9 or newer; stdin and the arguments pass through unchanged. If no
rem suitable Python is found it prints one line to stderr and exits 0: a missing Python must never
rem block the user's tool calls. The version probes read nul so the hook's JSON input is kept.
rem Keep CRLF line endings (cmd.exe needs them for labels; .gitattributes pins it).
setlocal
if "%~1"=="" (
  echo plumb: run.cmd needs a script name; hook skipped 1>&2
  exit /b 0
)
set "PLUMB_SCRIPT=%~dp0%~1"
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" <nul >nul 2>&1 && goto py3
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" <nul >nul 2>&1 && goto python
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" <nul >nul 2>&1 && goto python3
echo plumb: no Python 3.9+ found (tried py -3, python, python3); Plumb hook skipped 1>&2
exit /b 0

:py3
rem PLUMB_PYTHON tells the hook how the user starts Python, for the commands it prints.
set "PLUMB_PYTHON=py -3"
py -3 "%PLUMB_SCRIPT%" %2 %3 %4
exit /b %ERRORLEVEL%

:python
set "PLUMB_PYTHON=python"
python "%PLUMB_SCRIPT%" %2 %3 %4
exit /b %ERRORLEVEL%

:python3
set "PLUMB_PYTHON=python3"
python3 "%PLUMB_SCRIPT%" %2 %3 %4
exit /b %ERRORLEVEL%
