#!/usr/bin/env python3
"""Render a Mente Apex client deliverable: Legal/ Markdown (source of truth) → on-brand HTML/PDF.

Zero third-party dependencies (stdlib only) — the plugin is config-synced across
machines and must not depend on `pip install` on a fresh box. The Markdown subset is
bounded to what our own Legal/ templates use, not arbitrary CommonMark.
"""

from __future__ import annotations

import argparse
import html as _html
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# --- Pure transforms ---------------------------------------------------------

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# A fill-in slot is [bracketed prose] NOT immediately followed by "(" (which would
# make it a Markdown link label, e.g. [text](url)). A purely numeric bracket like [1]
# is a footnote/reference marker, not a slot — a real slot always carries descriptive
# prose — so the leading negative lookahead excludes it.
_PLACEHOLDER_RE = re.compile(r"\[(?!\s*\d+\s*\])[^\[\]]+\](?!\()")


def strip_comments(markdown: str) -> str:
    """Remove `<!-- ... -->` guidance blocks — instructions to the author, never shipped."""
    return _COMMENT_RE.sub("", markdown)


def find_placeholders(markdown: str) -> list[str]:
    """Return every unfilled `[placeholder]` slot, in order.

    Markdown links (`[label](url)`) are excluded — they are content, not fill-ins.
    """
    return _PLACEHOLDER_RE.findall(markdown)


# --- Markdown → HTML (bounded subset our Legal/ templates use) ----------------

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_HR_RE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
_UL_RE = re.compile(r"^\s*[-*]\s+(.*)$")
_OL_RE = re.compile(r"^\s*\d+\.\s+(.*)$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")


def _inline(text: str) -> str:
    """Escape HTML then apply inline Markdown: links, bold, italic."""
    text = _html.escape(text, quote=False)
    text = _LINK_RE.sub(r'<a href="\2">\1</a>', text)
    text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = _ITALIC_RE.sub(r"<em>\1</em>", text)
    return text


def _split_row(row: str) -> list[str]:
    """Split a pipe-table row into trimmed cells, dropping optional edge pipes."""
    cells = row.split("|")
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return [cell.strip() for cell in cells]


def markdown_to_html(markdown: str) -> str:
    """Convert the template Markdown subset to an HTML fragment.

    Block-level, line-driven: headings, hr, blockquote, ordered/unordered lists,
    GFM pipe tables, and paragraphs — with inline formatting applied to text.
    """
    lines = markdown.split("\n")
    out: list[str] = []
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]

        if line.strip() == "":
            index += 1
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2).strip())}</h{level}>")
            index += 1
            continue

        if _HR_RE.match(line):
            out.append("<hr>")
            index += 1
            continue

        # Pipe table: a row containing "|" immediately followed by a separator row.
        if "|" in line and index + 1 < total and _TABLE_SEP_RE.match(lines[index + 1]):
            header = _split_row(line)
            index += 2  # consume header + separator
            body_rows: list[list[str]] = []
            while index < total and "|" in lines[index] and lines[index].strip():
                body_rows.append(_split_row(lines[index]))
                index += 1
            head_html = "".join(f"<th>{_inline(cell)}</th>" for cell in header)
            rows_html = "".join(
                "<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>"
                for row in body_rows
            )
            out.append(
                f"<table><thead><tr>{head_html}</tr></thead><tbody>{rows_html}</tbody></table>"
            )
            continue

        if _UL_RE.match(line):
            items = []
            while index < total and _UL_RE.match(lines[index]):
                items.append(
                    f"<li>{_inline(_UL_RE.match(lines[index]).group(1).strip())}</li>"
                )
                index += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue

        if _OL_RE.match(line):
            items = []
            while index < total and _OL_RE.match(lines[index]):
                items.append(
                    f"<li>{_inline(_OL_RE.match(lines[index]).group(1).strip())}</li>"
                )
                index += 1
            out.append("<ol>" + "".join(items) + "</ol>")
            continue

        if line.lstrip().startswith(">"):
            quote_lines = []
            while index < total and lines[index].lstrip().startswith(">"):
                quote_lines.append(lines[index].lstrip()[1:].lstrip())
                index += 1
            out.append(
                "<blockquote>" + _inline(" ".join(quote_lines)) + "</blockquote>"
            )
            continue

        # Paragraph: consecutive non-blank lines that aren't another block.
        para_lines = []
        while (
            index < total
            and lines[index].strip() != ""
            and not _is_block_start(lines, index)
        ):
            para_lines.append(lines[index].strip())
            index += 1
        out.append("<p>" + _inline(" ".join(para_lines)) + "</p>")

    return "\n".join(out)


def _starts_table(lines: list[str], index: int) -> bool:
    """True if this line is a table header row followed by its separator row."""
    return (
        "|" in lines[index]
        and index + 1 < len(lines)
        and bool(_TABLE_SEP_RE.match(lines[index + 1]))
    )


def _is_block_start(lines: list[str], index: int) -> bool:
    """True if the line begins a non-paragraph block (stops paragraph accumulation)."""
    line = lines[index]
    if (
        _HEADING_RE.match(line)
        or _HR_RE.match(line)
        or _UL_RE.match(line)
        or _OL_RE.match(line)
    ):
        return True
    if line.lstrip().startswith(">"):
        return True
    return _starts_table(lines, index)


# --- Completeness gate -------------------------------------------------------


def check(markdown: str) -> list[str]:
    """Placeholders remaining after stripping guidance comments (the ship gate).

    Comments legitimately contain `[bracketed]` examples the author must NOT ship,
    so we strip them before counting — only slots in real content block a render.
    """
    return find_placeholders(strip_comments(markdown))


# --- Brand-book-first token wiring -------------------------------------------


@dataclass
class ResolvedBrand:
    """The live brand assets a render consults, plus any operator warning."""

    tokens_css: str
    fonts_css: str
    wordmark_svg: str
    source: Path | None
    warning: str = ""


def brand_is_stale(brand_root: Path) -> bool:
    """True if `brand-book.html` is newer than the generated `tokens/tokens.css`.

    The renderer never regenerates tokens itself (that logic stays single-sourced in
    the Brand repo); it only nudges when the book has moved ahead of its output.
    """
    book = Path(brand_root) / "brand-book.html"
    tokens = Path(brand_root) / "tokens" / "tokens.css"
    if not book.exists() or not tokens.exists():
        return False
    return book.stat().st_mtime > tokens.stat().st_mtime


def _read_if(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def _first_existing(*candidates: Path) -> Path | None:
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def resolve_brand(brand_root: Path, fallback_dir: Path | None = None) -> ResolvedBrand:
    """Resolve the brand assets a render consults, each from its canonical source.

    - **tokens.css** is the live brand-decision layer (colours, type scale) — read
      fresh from `Brand/tokens/tokens.css` every render so brand edits flow through.
    - **fonts.css** (embedded typefaces) and the **wordmark** are stable infra that
      change only on a major rebrand — preferred from the Brand source, else the
      vendored copy beside the skill.

    Never copies or runs a Brand script. If the live tokens can't be found, fall back
    to the vendored snapshot and flag the render as possibly stale rather than abort.
    """
    brand_root = Path(brand_root)
    fallback = Path(fallback_dir) if fallback_dir else None

    live_tokens = brand_root / "tokens" / "tokens.css"
    tokens_path = _first_existing(
        live_tokens, fallback / "tokens.css" if fallback else None
    )
    fonts_path = _first_existing(
        brand_root / "tokens" / "fonts.css",
        brand_root / "fonts.css",
        fallback / "fonts.css" if fallback else None,
    )
    wordmark_path = _first_existing(
        brand_root / "logo-exports" / "svg" / "mente-apex-wordmark-mono-seafoam.svg",
        fallback / "wordmark.svg" if fallback else None,
    )

    warning = ""
    source = brand_root if tokens_path == live_tokens else None
    if source is None:
        warning = (
            f"⚠ Brand source not found at {brand_root} — using vendored fallback "
            "tokens; output may not reflect the current brand book."
        )
    elif brand_is_stale(brand_root):
        warning = (
            "⚠ brand tokens may be stale — run Brand/tokens/build_tokens.py "
            "(brand-book.html is newer than tokens.css)"
        )

    return ResolvedBrand(
        tokens_css=_read_if(tokens_path) if tokens_path else "",
        fonts_css=_read_if(fonts_path) if fonts_path else "",
        wordmark_svg=_read_if(wordmark_path) if wordmark_path else "",
        source=source,
        warning=warning,
    )


# --- Document assembly (brand shell) -----------------------------------------

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


def _default_shell() -> str:
    return (_ASSETS_DIR / "shell.html").read_text()


def _masthead(
    title: str, wordmark_svg: str, meta: dict[str, str] | None, doc_kicker: str
) -> str:
    """The identity page: wordmark opens the document, then title + meta."""
    meta = meta or {}
    meta_cells = "".join(
        f'<div><span class="lbl">{_html.escape(label)}</span>'
        f'<span class="val">{_html.escape(value)}</span></div>'
        for label, value in meta.items()
    )
    return (
        '<section class="masthead">'
        f'<div class="mh-top"><span class="wm">{wordmark_svg}</span>'
        f'<span class="doc">{_html.escape(doc_kicker)}</span></div>'
        f"<h1>{_html.escape(title)}</h1>"
        f'<div class="mh-meta">{meta_cells}</div>'
        "</section>"
    )


def build_document(
    markdown: str,
    brand: ResolvedBrand,
    *,
    kind: str,
    lang: str,
    title: str | None = None,
    meta: dict[str, str] | None = None,
    doc_kicker: str = "",
    footer: str = "Mente Apex · menteapex.com",
    shell: str | None = None,
) -> str:
    """Assemble a filled Markdown deliverable into the on-brand HTML shell.

    `kind="identity"` prepends the full-bleed navy masthead (sales documents);
    `kind="letterhead"` is a plain M-margin page (legal / ops documents).
    """
    shell = shell if shell is not None else _default_shell()
    body_html = markdown_to_html(strip_comments(markdown))

    content = f'<main class="doc-body">{body_html}</main>'
    if footer:
        content += f'<footer class="doc-footer">{_html.escape(footer)}</footer>'
    if kind == "identity":
        content = _masthead(title or "", brand.wordmark_svg, meta, doc_kicker) + content

    return (
        shell.replace("{{LANG}}", lang)
        .replace("{{TITLE}}", _html.escape(title or "Mente Apex"))
        .replace("{{FONTS_CSS}}", brand.fonts_css)
        .replace("{{TOKENS_CSS}}", brand.tokens_css)
        .replace("{{CONTENT}}", content)
    )


# --- PDF glue + CLI ----------------------------------------------------------


def _default_brand_root() -> Path:
    business = os.environ.get(
        "BUSINESS_ROOT", str(Path.home() / "Documents" / "Business")
    )
    return Path(os.environ.get("BRAND_ROOT", str(Path(business) / "Brand")))


def _find_chrome() -> str | None:
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        shutil.which("google-chrome-stable"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _file_url(path: Path) -> str:
    """Absolute, percent-encoded file:// URI for Chrome.

    A relative path (e.g. from `--out .`) would otherwise yield `file://out/x.html`,
    where Chrome reads "out" as the host and prints an error page into the PDF.
    """
    return Path(path).resolve().as_uri()


def html_to_pdf(html_path: Path, pdf_path: Path) -> bool:
    """Render a self-contained HTML file to PDF via headless Chrome. Returns success."""
    chrome = _find_chrome()
    if not chrome:
        print(
            "⚠ Chrome/Chromium not found — skipping PDF; HTML written.", file=sys.stderr
        )
        return False
    pdf_path = Path(pdf_path).resolve()
    subprocess.run(
        [
            chrome,
            "--headless=new",
            "--run-all-compositor-stages-before-draw",
            f"--print-to-pdf={pdf_path}",
            "--no-pdf-header-footer",
            _file_url(html_path),
        ],
        check=False,
        capture_output=True,
    )
    return pdf_path.exists() and pdf_path.stat().st_size > 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a Mente Apex client deliverable."
    )
    parser.add_argument("markdown", help="Filled Legal/ Markdown template.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 and list any unfilled [placeholder]; render nothing.",
    )
    parser.add_argument("--lang", default="en", help="en | es-ES | es-419 | hr")
    parser.add_argument(
        "--kind", default="letterhead", choices=["identity", "letterhead"]
    )
    parser.add_argument("--title", default=None)
    parser.add_argument(
        "--out", default=None, help="Output directory (default: alongside input)."
    )
    parser.add_argument(
        "--brand-root", default=None, help="Override the Brand/ source location."
    )
    args = parser.parse_args(argv)

    source = Path(args.markdown)
    markdown = source.read_text()

    remaining = check(markdown)
    if args.check:
        if remaining:
            print("Unfilled placeholders — fill these before rendering:")
            for placeholder in remaining:
                print(f"  {placeholder}")
            return 1
        print("✓ no placeholders remain")
        return 0

    if remaining:
        print("✗ refusing to render: unfilled placeholders remain:", file=sys.stderr)
        for placeholder in remaining:
            print(f"  {placeholder}", file=sys.stderr)
        return 1

    brand_root = Path(args.brand_root) if args.brand_root else _default_brand_root()
    brand = resolve_brand(brand_root, fallback_dir=_ASSETS_DIR)
    if brand.warning:
        print(brand.warning, file=sys.stderr)

    html = build_document(
        markdown, brand, kind=args.kind, lang=args.lang, title=args.title
    )

    out_dir = Path(args.out) if args.out else source.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{source.stem}.html"
    html_path.write_text(html)

    pdf_path = out_dir / f"{source.stem}.pdf"
    if html_to_pdf(html_path, pdf_path):
        print(f"PDF: {pdf_path}")
    print(f"HTML: {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
