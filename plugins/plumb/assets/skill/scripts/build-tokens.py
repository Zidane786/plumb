#!/usr/bin/env python3
"""build-tokens.py: turn the one tokens JSON into the web CSS (and, in later versions, mobile themes and evidence).

Usage: build-tokens.py [--check] [--root SKILL_DIR] [--project PATH]

Reads <skill>/assets/tokens/*.tokens.json (exactly one) and the web template, writes
<skill>/assets/platforms/web/tokens.css (+ tailwind.tokens.js for tailwind-v3) and the copies listed in
$extensions.plumb.web.copies (relative to the project root). --check writes nothing: it exits 1 naming every stale or
missing file. Exit codes: 0 ok, 1 stale (--check), 2 bad input (error: ... then fix: ...).

Python 3.9+, standard library only. Declarations follow the order of the tokens file
(deterministic, keeps the file's grouping). Imports the shared core _plumb.py from its own directory.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _plumb as P  # noqa: E402
from _plumb import PlumbError  # noqa: E402

STYLINGS = ("tailwind-v4", "tailwind-v3", "css")
TEMPLATE_NAME = "tokens.css.template"
SCRIPT_REL = "scripts/build-tokens.py"


def _err(what: str, fix: str) -> PlumbError:
    return PlumbError(f"error: {what}\nfix: {fix}")


# ---------------------------------------------------------------- locations


def find_project_root(skill_dir: Path, project: Optional[Path] = None) -> Path:
    """Ruling A: nearest ancestor of the skill dir holding PLUMB.md, else --project, else skill_dir.parents[2]."""
    skill_dir = Path(skill_dir).resolve()
    for parent in skill_dir.parents:
        if (parent / "PLUMB.md").is_file():
            return parent
    if project is not None:
        return Path(project).resolve()
    parents = skill_dir.parents
    return parents[2] if len(parents) > 2 else skill_dir


def rel(path: Path, root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def find_tokens_file(skill_dir: Path) -> Path:
    folder = skill_dir / "assets" / "tokens"
    found = sorted(folder.glob("*.tokens.json")) if folder.is_dir() else []
    if len(found) == 1:
        return found[0]
    if not found:
        raise _err(
            f"no tokens file in {folder} (expected one *.tokens.json)",
            "run the project's create or extract step to make the tokens file, or pass --root with the skill folder",
        )
    names = ", ".join(f.name for f in found)
    raise _err(f"several tokens files in {folder}: {names}", "keep exactly one *.tokens.json there and move the others away")


# ---------------------------------------------------------------- value formatting


def num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else repr(float(x)).rstrip("0").rstrip(".")


def dimension_css(v: object) -> str:
    """A dimension or duration as CSS: '16px' as given, {value, unit} -> '16px', a bare number as is."""
    if isinstance(v, dict) and "value" in v:
        unit = v.get("unit", "")
        return f"{num(v['value'])}{unit}" if isinstance(v["value"], (int, float)) else f"{v['value']}{unit}"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return num(v)
    if isinstance(v, str):
        return v
    raise _err(f"not a dimension: {v!r}", 'write it as "16px" or {"value": 16, "unit": "px"}')


def color_css(v: object) -> str:
    hexv, alpha = P.parse_color(v)
    if alpha >= 1:
        return hexv
    r, g, b = int(hexv[1:3], 16), int(hexv[3:5], 16), int(hexv[5:7], 16)
    return f"rgb({r} {g} {b} / {alpha:.2f})"


def _is_color(v: object) -> bool:
    return isinstance(v, dict) and "colorSpace" in v


def value_css(v: object, ttype: Optional[str]) -> str:
    if ttype == "color" or _is_color(v):
        return color_css(v)
    if ttype == "cubicBezier" and isinstance(v, list):
        return "cubic-bezier(" + ", ".join(num(x) for x in v) + ")"
    if ttype == "fontFamily":
        if isinstance(v, list):
            return ", ".join(f'"{f}"' if " " in str(f) else str(f) for f in v)
        return str(v)
    if ttype == "shadow":
        layers = v if isinstance(v, list) else [v]
        out = []
        for layer in layers:
            if isinstance(layer, str):
                out.append(layer)
                continue
            if not isinstance(layer, dict):
                raise _err(f"not a shadow value: {layer!r}", "use a list of {offsetX, offsetY, blur, spread, color} objects")
            parts = [dimension_css(layer.get(k, "0px")) for k in ("offsetX", "offsetY", "blur")]
            spread = dimension_css(layer.get("spread", "0px"))
            if spread not in ("0", "0px"):
                parts.append(spread)
            parts.append(color_css(layer.get("color", "#000000")))
            out.append(("inset " if layer.get("inset") else "") + " ".join(parts))
        return ", ".join(out)
    if ttype in ("dimension", "duration") or (isinstance(v, dict) and "unit" in v):
        return dimension_css(v)
    if isinstance(v, bool):
        raise _err(f"cannot format {v!r} as CSS", "use a string or a number")
    if isinstance(v, (int, float)):
        return num(v)
    if isinstance(v, str):
        return v
    raise _err(f"cannot format {v!r} as CSS", "check the token's $type and $value")


# ---------------------------------------------------------------- variables from tokens


_ALIAS = re.compile(r"^\{([A-Za-z0-9_.-]+)\}$")
FIELD_TYPES = {"fontSize": "dimension", "lineHeight": "dimension", "letterSpacing": "dimension", "fontFamily": "fontFamily"}
TYPO_FIELDS = (("fontSize", ""), ("lineHeight", "--line-height"), ("letterSpacing", "--letter-spacing"),
               ("fontWeight", "--font-weight"), ("fontFamily", "--font-family"))


def varname(path: str) -> str:
    parts = path.split(".")
    group, rest = parts[0], "-".join(parts[1:])
    if group == "motion" and len(parts) > 2:
        sub = "-".join(parts[2:])
        if parts[1] == "duration":
            return f"--duration-{sub}"
        if parts[1] == "easing":
            return f"--ease-{sub}"
        return f"--motion-{parts[1]}-{sub}"
    if group == "color":
        return f"--color-{rest}"
    if group == "label":
        return f"--color-label-{rest}"
    if group == "typography":
        return f"--text-{rest}"
    return f"--{group}-{rest}" if rest else f"--{group}"


def _token_ext(token: dict) -> dict:
    ext = token.get("$extensions")
    ext = ext.get(P.EXT) if isinstance(ext, dict) else None
    return ext if isinstance(ext, dict) else {}


def _alias_target(raw: object) -> Optional[str]:
    m = _ALIAS.match(raw) if isinstance(raw, str) else None
    return m.group(1) if m else None


def _decls(doc: dict, path: str, token: dict, ttype: Optional[str], mode: str) -> List[Tuple[str, str]]:
    """The (custom property, value) pairs one token contributes in a mode (light | dark | md)."""
    name = varname(path)
    ext = _token_ext(token)
    try:
        value = P.resolve(doc, path, mode)
        if ttype == "typography" and isinstance(value, dict):
            base = P.resolve(doc, path, "light")
            out = []
            for key, suffix in TYPO_FIELDS:
                if key in value and (mode == "light" or value[key] != base.get(key)):
                    out.append((name + suffix, value_css(value[key], FIELD_TYPES.get(key))))
            return out
        raw = ext[mode] if mode in ext else token["$value"]
        target = _alias_target(raw)
        if target is not None and not isinstance(value, dict) and ttype != "typography":
            return [(name, f"var({varname(target)})")]
        return [(name, value_css(value, ttype))]
    except PlumbError as exc:
        text = str(exc)
        if text.startswith(f"error: {path}") or "token reference cycle" in text or "unknown token" in text:
            raise
        first, _, rest = text.partition("\n")
        raise PlumbError(f"error: {path}: {first[len('error: '):]}\n{rest}") from None


def declarations(doc: dict, mode: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for path, token, ttype in P.iter_tokens(doc):
        if mode != "light" and mode not in _token_ext(token):
            continue
        out.extend(_decls(doc, path, token, ttype, mode))
    return out


# ---------------------------------------------------------------- template


PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9._-]+)(@dark|@md)?(?:\|([a-z]+))?\s*\}\}")
DIRECTIVE_LINE = re.compile(r"^([ \t]*)\{\{@([A-Za-z0-9-]+)\}\}[ \t]*$", re.M)
IF_MD = re.compile(r"^[ \t]*\{\{@if-md\}\}[ \t]*\n.*?^[ \t]*\{\{@end\}\}[ \t]*\n\n?", re.M | re.S)
DIRECTIVE_ANY = re.compile(r"\{\{@([A-Za-z0-9-]+)\}\}")


def header_text(skill_dir: Path, tokens_file: Path, root: Path) -> str:
    script = rel(skill_dir / SCRIPT_REL, root)
    src = rel(tokens_file, root)
    return f"GENERATED by {script} from {src}. Do not edit: edit the tokens JSON, then run build-tokens.py."


def read_template(skill_dir: Path, styling: str) -> str:
    folder = skill_dir / "assets" / "platforms" / "web"
    for name in (TEMPLATE_NAME, f"{TEMPLATE_NAME}.{styling}"):
        path = folder / name
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError) as exc:
                raise _err(f"{path}: cannot read the template ({exc})", "save it as UTF-8") from None
            return text.replace("\r\n", "\n").replace("\r", "\n")
    raise _err(
        f"missing web template {folder / TEMPLATE_NAME}",
        f"copy {TEMPLATE_NAME}.{styling} from the Plumb plugin's assets/skill/assets/platforms/web/ to {folder / TEMPLATE_NAME}",
    )


def _lines(decls: List[Tuple[str, str]]) -> List[str]:
    return [f"{n}: {v};" for n, v in decls]


def build_css(doc: dict, template: str, header: str) -> str:
    directives: Dict[str, Callable[[], List[str]]] = {
        "header": lambda: [header],
        "vars": lambda: _lines(declarations(doc, "light")),
        "vars-dark": lambda: _lines(declarations(doc, "dark")),
        "vars-md": lambda: _lines(declarations(doc, "md")),
    }

    def run_directive(name: str) -> List[str]:
        if name not in directives:
            raise _err(f"unknown template directive {{{{@{name}}}}}", f"use one of: {', '.join('@' + d for d in directives)}")
        return directives[name]()

    def block(m: "re.Match[str]") -> str:
        lines = run_directive(m.group(2))
        if not lines:
            return "\x00DROP\x00"
        return "\n".join(m.group(1) + line for line in lines)

    if not directives["vars-md"]():  # no md tokens: drop the whole {{@if-md}} ... {{@end}} section
        template = IF_MD.sub("", template)
    template = re.sub(r"^[ \t]*\{\{@(?:if-md|end)\}\}[ \t]*\n", "", template, flags=re.M)
    out = DIRECTIVE_LINE.sub(block, template)
    out = re.sub(r"\x00DROP\x00\n?", "", out)
    out = DIRECTIVE_ANY.sub(lambda m: " ".join(run_directive(m.group(1))), out)

    def sub(m: "re.Match[str]") -> str:
        path, variant, flt = m.group(1), m.group(2), m.group(3)
        mode = {"@dark": "dark", "@md": "md"}.get(variant or "", "light")
        try:
            v = P.resolve(doc, path, mode)
        except PlumbError as exc:
            raise _err(f"template placeholder {m.group(0)}: {str(exc).splitlines()[0][len('error: '):]}",
                       "fix the name in the template or add the token to the tokens file") from None
        if flt == "percent":
            return num(round(float(v) * 100, 4)) + "%"
        if flt == "s":
            text = dimension_css(v)
            mm = re.fullmatch(r"([\d.]+)ms", text)
            if not mm:
                raise _err(f"{m.group(0)}: |s needs a duration in ms, got {text}", "use a duration token written like 150ms")
            return num(float(mm.group(1)) / 1000) + "s"
        if flt:
            raise _err(f"unknown filter |{flt} in {m.group(0)}", "use |percent or |s")
        token_type = _type_of(doc, path)
        return value_css(v, token_type)

    out = PLACEHOLDER.sub(sub, out)
    left = re.search(r"\{\{[^}]*\}\}", out)
    if left:
        raise _err(f"unresolved placeholder in the template: {left.group(0)}", "use {{group.token}}, {{group.token@dark}} or {{@vars}}")
    if "GENERATED by" not in out[:400]:
        out = f"/* {header} */\n" + out
    return out


def _type_of(doc: dict, path: str) -> Optional[str]:
    for p, _tok, ttype in P.iter_tokens(doc):
        if p == path:
            return ttype
    parent = path.rsplit(".", 1)[0]  # a field of a composite, e.g. typography.sm.fontSize
    for p, _tok, ttype in P.iter_tokens(doc):
        if p == parent:
            field = path.rsplit(".", 1)[1]
            return FIELD_TYPES.get(field)
    return None


# ---------------------------------------------------------------- tailwind v3 map


def build_tailwind_js(doc: dict, header: str) -> str:
    sections: Dict[str, Dict[str, object]] = {k: {} for k in ("colors", "borderRadius", "spacing", "boxShadow", "fontFamily",
                                                              "fontSize", "transitionDuration", "transitionTimingFunction")}
    for path, _tok, ttype in P.iter_tokens(doc):
        parts = path.split(".")
        group, key = parts[0], "-".join(parts[1:])
        ref = f"var({varname(path)})"
        if group == "color":
            sections["colors"][key] = ref
        elif group == "label":
            sections["colors"][f"label-{key}"] = ref
        elif group == "radius":
            sections["borderRadius"][key] = ref
        elif group == "spacing":
            sections["spacing"][key] = ref
        elif group == "shadow":
            sections["boxShadow"][key] = ref
        elif group == "font":
            sections["fontFamily"][key] = ref
        elif group == "typography":
            value = P.resolve(doc, path)
            extra = {}
            if isinstance(value, dict):
                for field, suffix in (("lineHeight", "--line-height"), ("letterSpacing", "--letter-spacing"),
                                      ("fontWeight", "--font-weight")):
                    if field in value:
                        extra[field] = f"var({varname(path)}{suffix})"
            sections["fontSize"][key] = [ref, extra]
        elif group == "motion" and len(parts) > 2 and parts[1] == "duration":
            sections["transitionDuration"]["-".join(parts[2:])] = ref
        elif group == "motion" and len(parts) > 2 and parts[1] == "easing":
            sections["transitionTimingFunction"]["-".join(parts[2:])] = ref
    body = {k: v for k, v in sections.items() if v}
    text = json.dumps(body, indent=2, ensure_ascii=False)
    return (
        f"/* {header} */\n"
        "/* Use in tailwind.config.js: theme: { extend: require('./path/to/tailwind.tokens.js') } */\n"
        f"module.exports = {text};\n"
    )


# ---------------------------------------------------------------- outputs


def safe_copy_path(root: Path, copy: object) -> Path:
    text = str(copy).replace("\\", "/") if isinstance(copy, str) else ""
    bad = (not text or text.startswith("/") or re.match(r"^[A-Za-z]:", text) is not None
           or ".." in text.split("/"))
    if bad:
        raise _err(
            f"$extensions.plumb.web.copies has {copy!r}, which is not a path inside the project",
            "write copies relative to the project root, e.g. \"app/globals.css\"",
        )
    return (root / text).resolve()


def outputs(doc: dict, skill_dir: Path, project: Optional[Path] = None, tokens_file: Optional[Path] = None) -> Dict[Path, str]:
    """Every generated file as {absolute path: content}. Later tasks extend this with mobile themes and evidence."""
    skill_dir = Path(skill_dir).resolve()
    root = find_project_root(skill_dir, project)
    tokens_file = tokens_file or find_tokens_file(skill_dir)
    settings = P.plumb_settings(doc)
    web = settings["web"]
    styling = web["styling"]
    if styling not in STYLINGS:
        raise _err(f"web.styling is {styling!r} in {tokens_file.name}", f"set $extensions.plumb.web.styling to one of: {', '.join(STYLINGS)}")
    header = header_text(skill_dir, tokens_file, root)
    css = build_css(doc, read_template(skill_dir, styling), header)
    folder = skill_dir / "assets" / "platforms" / "web"
    out: Dict[Path, str] = {folder / "tokens.css": css}
    if styling == "tailwind-v3":
        out[folder / "tailwind.tokens.js"] = build_tailwind_js(doc, header)
    copies = web.get("copies") or []
    if not isinstance(copies, list):
        raise _err("web.copies must be a list of paths", "write it as [\"app/globals.css\"]")
    for copy in copies:
        out[safe_copy_path(root, copy)] = css
    return dict(sorted(out.items(), key=lambda kv: str(kv[0])))


# ---------------------------------------------------------------- cli


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # shaped like every other refusal
        self.exit(2, f"error: {message}\nfix: python3 {SCRIPT_REL} [--check] [--root SKILL_DIR] [--project PATH]\n")


def main(argv: Optional[List[str]] = None) -> int:
    P.utf8_stdio()
    parser = _Parser(prog="build-tokens.py", description="Build the web token outputs from the tokens JSON.")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 when any output is stale or missing")
    parser.add_argument("--root", metavar="SKILL_DIR", help="the design-system skill folder (default: this script's skill)")
    parser.add_argument("--project", metavar="PATH", help="project root when no PLUMB.md is found above the skill")
    args = parser.parse_args(argv)
    skill_dir = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    project = Path(args.project) if args.project else None
    try:
        root = find_project_root(skill_dir, project)
        tokens_file = find_tokens_file(skill_dir)
        files = outputs(P.load_tokens(tokens_file), skill_dir, project, tokens_file)
    except PlumbError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
        print(
            f"error: unexpected token structure ({type(exc).__name__}: {exc})\n"
            f"fix: open the tokens file and compare it with reference/tokens-format.md",
            file=sys.stderr,
        )
        return 2
    command = f"python3 {rel(skill_dir / SCRIPT_REL, root)}"
    stale = []
    for path, text in files.items():
        try:
            current = path.read_bytes() if path.exists() else None
        except OSError:
            current = None
        if current == text.encode("utf-8"):
            continue
        if args.check:
            stale.append(path)
            continue
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        except OSError as exc:
            print(f"error: cannot write {rel(path, root)} ({exc})\nfix: check the folder exists and is writable", file=sys.stderr)
            return 2
        print(f"wrote {rel(path, root)}")
    if args.check:
        if stale:
            for path in stale:
                print(f"stale: {rel(path, root)}")
            print(f"fix: {command}")
            return 1
        print(f"ok: {len(files)} generated files are up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
