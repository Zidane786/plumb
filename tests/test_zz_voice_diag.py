# Diagnostic only (branch diag/ring-macos, never merged): how long the no-voice tour takes to reach step 2 on a runner.
import json
import time

import pytest
from test_tours import _open, DEMO_PAGE, NO_VOICES, REMOTE_VOICES, VOICE_BTN, browser, voiced  # noqa: F401

STATE = "JSON.stringify(window.plumbPlayer.state())"
# the player's own record: when each position started (the test pages log it as window.__log)
LOG = "JSON.stringify((window.__log || []).slice(-6))"
CHOOSE = """() => { const v = document.querySelector('[data-pl=start-voice]'), q = document.querySelector('[data-pl=start-quiet]');
  const voice = !!v && !v.hidden && v.offsetParent !== null; (voice ? v : q).click(); return voice; }"""


@pytest.mark.parametrize("run", range(15))
@pytest.mark.parametrize("init", [NO_VOICES, "window.__voicesLater = 300;" + REMOTE_VOICES], ids=["none", "late-remote"])
def test_voice_diag(browser, voiced, init, run):
    ctx, page, errors, _ = _open(browser, voiced / DEMO_PAGE, init=init)
    try:
        page.wait_for_function("window.plumbPlayer.state().waiting")
        a = time.monotonic()
        voice = page.evaluate(CHOOSE)
        page.wait_for_function(f"document.querySelector('{VOICE_BTN}').disabled", timeout=10000)
        b = time.monotonic()
        page.wait_for_function("window.plumbPlayer.state().pos === 1", timeout=20000)
        c = time.monotonic()
        slow = c - b > 2
        print(f"\nVDIAG {init[:20]!r} run={run} voice_clicked={voice} to_disabled={b - a:.2f}s to_pos1={c - b:.2f}s"
              f" slow={slow}")
        if slow:
            print("VDIAG state", page.evaluate(STATE), "log", page.evaluate(LOG), "errors", json.dumps(errors))
    finally:
        ctx.close()
