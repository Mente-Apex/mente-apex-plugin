import base64
import re
import sys
import urllib.request

CSS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,500&"
    "family=DM+Sans:wght@300;400;500&display=swap"
)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

req = urllib.request.Request(CSS_URL, headers={"User-Agent": UA})
css = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")

urls = sorted(set(re.findall(r"url\((https://[^)]+\.woff2)\)", css)))
print(f"font files: {len(urls)}", file=sys.stderr)
cache = {}
for u in urls:
    data = urllib.request.urlopen(
        urllib.request.Request(u, headers={"User-Agent": UA}), timeout=30
    ).read()
    cache[u] = "data:font/woff2;base64," + base64.b64encode(data).decode()


def repl(m):
    return f"url({cache[m.group(1)]})"


embedded = re.sub(r"url\((https://[^)]+\.woff2)\)", repl, css)

with open(".build/fonts.css", "w") as f:
    f.write(embedded)
print(
    f"wrote .build/fonts.css ({len(embedded)} bytes, {len(cache)} fonts embedded)",
    file=sys.stderr,
)
