from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel

DOCS_DIR = Path(__file__).resolve().parent

DOC_ORDER = [
    "README.md",
    "installation.md",
    "getting-started.md",
    "conversing.md",
    "configuration.md",
    "harness-engineering.md",
    "tools.md",
    "workflows.md",
    "workflow-reference.md",
    "advanced-usage.md",
]


class DocEntry(BaseModel):
    slug: str
    title: str
    filename: str


class DocContent(BaseModel):
    slug: str
    title: str
    content: str


def slug_from_filename(filename: str) -> str:
    if filename == "README.md":
        return "readme"
    return filename.removesuffix(".md")


def title_from_content(content: str, filename: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    if filename == "README.md":
        return "README"
    return filename.removesuffix(".md").replace("-", " ").title()


def list_doc_entries() -> list[DocEntry]:
    entries: list[DocEntry] = []
    for filename in DOC_ORDER:
        path = DOCS_DIR / filename
        if path.is_file():
            content = path.read_text(errors="replace")
            entries.append(
                DocEntry(
                    slug=slug_from_filename(filename),
                    title=title_from_content(content, filename),
                    filename=filename,
                )
            )
    for path in sorted(DOCS_DIR.glob("*.md")):
        if path.name not in DOC_ORDER and path.name != "__init__.md":
            content = path.read_text(errors="replace")
            entries.append(
                DocEntry(
                    slug=slug_from_filename(path.name),
                    title=title_from_content(content, path.name),
                    filename=path.name,
                )
            )
    return entries


def read_doc_content(slug: str) -> DocContent:
    if slug == "readme":
        filename = "README.md"
    else:
        filename = f"{slug}.md"

    path = (DOCS_DIR / filename).resolve()
    try:
        path.relative_to(DOCS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Doc not found")

    content = path.read_text(errors="replace")
    return DocContent(
        slug=slug,
        title=title_from_content(content, filename),
        content=content,
    )
