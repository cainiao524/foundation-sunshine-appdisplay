#!/usr/bin/env python3
"""Map a release tag to the version string used in Windows asset filenames.

Short date tags of the form vYYYY.D or vYYYY.DDD are zero-padded to
vYYYY.MMDD (for example v2026.813 -> v2026.0813). Other tags are kept, minus
characters GitHub drops from asset names: v2026.1123.185102.杂鱼.appdisplay
becomes v2026.1123.185102.appdisplay (see scripts/publish_release.py).
"""

from __future__ import annotations

import re
import sys

_SHORT_DATE = re.compile(r"^v([0-9]{4})\.([0-9]+)$")


def asset_tag(tag: str) -> str:
    match = _SHORT_DATE.fullmatch(tag)
    if not match:
        ascii_tag = re.sub(r"[^A-Za-z0-9._-]", "", tag)
        return re.sub(r"\.{2,}", ".", ascii_tag).strip(".")
    year, date = match.group(1), match.group(2)
    return f"v{year}.{date.zfill(4)}"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: release_asset_tag.py <tag>", file=sys.stderr)
        return 2
    print(asset_tag(args[0]), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
