from __future__ import annotations

import re

from ..models import ScrcpyCapabilities


def parse_scrcpy_version(output: str) -> str:
    match = re.search(r"\bscrcpy\s+v?([0-9]+(?:\.[0-9]+)+(?:[-\w.]*)?)", output, re.I)
    return match.group(1) if match else "inconnue"


def parse_scrcpy_capabilities(version_output: str, help_output: str) -> ScrcpyCapabilities:
    options = set(re.findall(r"(?<!\w)(--[a-z][a-z0-9-]*)", help_output))
    return ScrcpyCapabilities(parse_scrcpy_version(version_output), options)

