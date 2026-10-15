"""Print the CHANGELOG.md section for a version (used by the release workflow)."""

import re
import sys

version = sys.argv[1]
text = open("CHANGELOG.md", encoding="utf-8").read()
match = re.search(rf"^## {re.escape(version)}\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
if match and match.group(1).strip():
    print(match.group(1).strip())
else:
    print(f"No notes for {version} in CHANGELOG.md.")
