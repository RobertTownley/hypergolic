import re

_HOOK = re.compile(r"^.+?\.{3,}(?:\(no files to check\))?(Passed|Skipped)$")
_PROGRESS = re.compile(r"\d+%|^Progress: |^[.sx]+\s*(\[|$)")
_SHAPE_KEY = re.compile(r"\d+|\.{2,}")


def _collapse_hooks(lines: list[str]) -> list[str]:
    out: list[str] = []
    counts = {"Passed": 0, "Skipped": 0}
    for line in lines:
        m = _HOOK.match(line)
        if m:
            counts[m[1]] += 1
            continue
        out.append(line)
    summary = ", ".join(f"{n} {k.lower()}" for k, n in counts.items() if n)
    return ([f"[hooks: {summary}]"] if summary else []) + out


def _collapse_progress(lines: list[str]) -> list[str]:
    out: list[str] = []
    run: list[str] = []
    for line in lines + [""]:
        key = _SHAPE_KEY.sub("#", line)
        if run and _PROGRESS.search(line) and _SHAPE_KEY.sub("#", run[-1]) == key:
            run.append(line)
            continue
        out += run if len(run) < 3 else [f"[{len(run) - 1} progress lines]", run[-1]]
        run = [line] if _PROGRESS.search(line) else []
        if not run:
            out.append(line)
    return out[:-1]


def shape_hook_text(text: str) -> str:
    lines = text.split("\n")
    shaped = _collapse_progress(_collapse_hooks(lines))
    return text if shaped == lines else "\n".join(shaped)
