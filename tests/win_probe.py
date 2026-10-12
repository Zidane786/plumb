"""TEMPORARY probe (removed in the next commit): how Windows shells pass a hook command's stderr and exit code."""
import base64
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

base = Path(tempfile.mkdtemp()) / "Café Ünïcode"
base.mkdir(parents=True)
child = base / "child.cmd"
child.write_bytes(('@echo off\r\n"' + sys.executable + '" -c "import sys; d=sys.stdin.buffer.read(); '
                   "sys.stdout.buffer.write(b'out:'+d); sys.stderr.buffer.write('err \\u00fc line\\n'.encode('utf-8')); "
                   'sys.exit(int(sys.argv[1]))" %1\r\nexit /b %ERRORLEVEL%\r\n').encode("utf-8"))


def q(t):
    return "'" + t.replace("'", "''") + "'"


def enc(body):
    return base64.b64encode(body.encode("utf-16-le")).decode("ascii")


s = str(child)
old = f"$s={q(s)}; if (Test-Path -LiteralPath $s) {{ & $s CODE; exit $LASTEXITCODE }}; exit 0"
new = ("$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; "
       f"$s={q(s)}; if (-not (Test-Path -LiteralPath $s)) {{ exit 0 }}; try {{ "
       "$i=New-Object System.Diagnostics.ProcessStartInfo; "
       "$i.FileName=[IO.Path]::Combine($env:SystemRoot,'System32','cmd.exe'); "
       "$i.Arguments='/d /s /c \"\"'+$s+'\" CODE\"'; "
       "$i.UseShellExecute=$false; $i.RedirectStandardInput=$true; $i.RedirectStandardOutput=$true; "
       "$i.RedirectStandardError=$true; $p=[Diagnostics.Process]::Start($i); "
       "$o=$p.StandardOutput.BaseStream.CopyToAsync([Console]::OpenStandardOutput()); "
       "$e=$p.StandardError.BaseStream.CopyToAsync([Console]::OpenStandardError()); "
       "[Console]::OpenStandardInput().CopyTo($p.StandardInput.BaseStream); $p.StandardInput.Close(); "
       "$p.WaitForExit(); $o.Wait(); $e.Wait(); exit $p.ExitCode } catch { exit 0 }")
variants = {}
for code in ("2", "0"):
    variants[f"old-{code}"] = "powershell -NoProfile -NonInteractive -EncodedCommand " + enc(old.replace("CODE", code))
    n = "powershell -NoProfile -NonInteractive -EncodedCommand " + enc(new.replace("CODE", code))
    variants[f"new-{code}"] = n
    variants[f"new-poly-{code}"] = n + " ; exit $LASTEXITCODE"
    variants[f"new-out-{code}"] = n.replace("-NonInteractive", "-NonInteractive -OutputFormat Text")
shells = {"cmd": lambda c: ["cmd", "/d", "/c", c],
          "ps51": lambda c: [shutil.which("powershell"), "-NoProfile", "-NonInteractive", "-Command", c],
          "bash": lambda c: [shutil.which("bash") or "bash", "-c", c]}
if shutil.which("pwsh"):
    shells["pwsh"] = lambda c: [shutil.which("pwsh"), "-NoProfile", "-NonInteractive", "-Command", c]
for vname, cmd in variants.items():
    for sname, mk in shells.items():
        try:
            r = subprocess.run(mk(cmd), input="{\"p\": \"Café\"}".encode("utf-8"), capture_output=True, timeout=60)
            print(f"{vname:12} {sname:5} rc={r.returncode} out={r.stdout[:80]!r} err={r.stderr[:160]!r}")
        except Exception as exc:
            print(f"{vname:12} {sname:5} EXC {exc!r}")
