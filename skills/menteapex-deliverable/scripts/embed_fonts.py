"""Regenerate `assets/fonts.css` with every brand webfont inlined as a data URI.

Run this only when the brand typefaces change. The output is committed, because
rendering a client deliverable must never depend on network access.

The families here MUST match `assets/tokens.css`. They did not: this script
fetched **DM Sans** while `--font-text` is **Manrope**, so regenerating produced
a stylesheet with no face matching the family the CSS asks for, and every
client PDF fell back to Arial/Helvetica — off-brand, and with different metrics
that reflow line breaks and repaginate the document. `_assert_families_match`
now makes that a hard failure instead of a silent one.
"""

import base64
import re
import sys
import urllib.request
from pathlib import Path

# Keep in lockstep with `--font-display` and `--font-text` in assets/tokens.css.
DISPLAY_FAMILY = "Cormorant Garamond"
TEXT_FAMILY = "Manrope"

CSS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,500&"
    "family=Manrope:wght@300;400;500&display=swap"
)

# Google Fonts serves woff2 only to browsers it recognises; a stdlib default
# User-Agent gets ttf, which is several times larger and not what the shipped
# stylesheet expects.
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
OUTPUT_PATH = _ASSETS_DIR / "fonts.css"
TOKENS_PATH = _ASSETS_DIR / "tokens.css"

_FONT_URL_RE = re.compile(r"url\((https://[^)]+\.woff2)\)")


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(request, timeout=30).read()


def _assert_families_match(tokens_css: str) -> None:
    """Fail loudly when this script and the brand tokens disagree.

    The whole defect was that nothing connected the two: the generator could
    name any family at all and the mismatch only showed up as wrong-looking
    PDFs at the client's end.
    """
    for family in (DISPLAY_FAMILY, TEXT_FAMILY):
        if f'"{family}"' not in tokens_css:
            raise SystemExit(
                f"✗ {family!r} is not named in {TOKENS_PATH}. This script and "
                "the brand tokens must agree, or the embedded faces will not "
                "match the families the CSS asks for and every deliverable "
                "will silently fall back to a system font."
            )


def main() -> int:
    _assert_families_match(TOKENS_PATH.read_text(encoding="utf-8"))

    css = _fetch(CSS_URL).decode("utf-8")
    urls = sorted(set(_FONT_URL_RE.findall(css)))
    if not urls:
        raise SystemExit(
            "✗ Google Fonts returned no woff2 URLs — refusing to write a "
            "stylesheet that embeds nothing."
        )
    print(f"font files: {len(urls)}", file=sys.stderr)

    embedded_by_url = {
        url: "data:font/woff2;base64," + base64.b64encode(_fetch(url)).decode()
        for url in urls
    }
    embedded = _FONT_URL_RE.sub(
        lambda match: f"url({embedded_by_url[match.group(1)]})", css
    )

    # Straight into assets/, which is where `resolve_brand` reads from. The old
    # relative `.build/fonts.css` did not exist in the repo and was never read
    # by anything, so the output had to be hand-copied into place.
    OUTPUT_PATH.write_text(embedded, encoding="utf-8")
    print(
        f"wrote {OUTPUT_PATH} ({len(embedded)} bytes, "
        f"{len(embedded_by_url)} faces embedded)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
