# Diagnostic only (branch diag/ring-macos, never merged): where the drawer step's ring lands on a macOS runner.
import json

import pytest
from test_tours import _open, _start, PROTO_REL, RINGS, RECT, browser, staged  # noqa: F401

SEL = '#pp-frame [data-screen="boxes"] p > .slide3'
INFO = """(sel) => {
  const t = document.querySelector(sel), st = t.closest('[data-state]'), f = document.getElementById('pp-frame');
  const fr = f.getBoundingClientRect(), layer = document.querySelector('.pl-layer');
  const lr = layer ? layer.getBoundingClientRect() : null;
  return { scrollY: window.scrollY, docH: document.documentElement.scrollHeight, innerH: window.innerHeight,
    sbw: window.innerWidth - document.documentElement.clientWidth,
    frame: [fr.top, fr.height], layer: lr ? [lr.top, lr.height, layer.parentElement.id || layer.parentElement.className] : null,
    blocks: [...st.children].map(c => [c.className || c.tagName, Math.round(c.getBoundingClientRect().top), c.offsetHeight]),
    fonts: document.fonts ? document.fonts.status : null };
}"""


@pytest.mark.parametrize("run", range(15))
@pytest.mark.parametrize("width", [390, 1280])
def test_ring_diag(browser, staged, width, run):
    ctx, page, errors, _ = _open(browser, staged / PROTO_REL, width=width)
    try:
        _start(page, "staged", "guide", step=16)
        early = [page.evaluate(RINGS), page.evaluate(RECT, SEL), page.evaluate(INFO, SEL)]
        page.wait_for_timeout(2000)
        late = [page.evaluate(RINGS), page.evaluate(RECT, SEL), page.evaluate(INFO, SEL)]
        page.evaluate("window.dispatchEvent(new Event('resize'))")
        page.wait_for_timeout(300)
        redrawn = [page.evaluate(RINGS), page.evaluate(RECT, SEL)]
        ok = late[0] and abs(late[0][0][1] - late[1][1]) <= 1
        print(f"\nDIAG width={width} run={run} ok={ok} browser={browser.version}")
        if not ok:
            print("DIAG early", json.dumps(early))
            print("DIAG late", json.dumps(late))
            print("DIAG redrawn", json.dumps(redrawn))
    finally:
        ctx.close()
