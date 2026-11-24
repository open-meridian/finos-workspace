"""The licence scan of what the plugin's image ships in Python: the plugin's
own distribution and every distribution it requires, followed through their
requirements as installed. A distribution under the AGPL, the GPL or the
SSPL fails it (the LGPL does not), as does one whose licence it cannot
read, since this fork is Apache-2.0 and its image is built from it. Prints
each distribution with its licence.

Usage: python open-meridian/ci/python_licences.py [DISTRIBUTION]
(`workspace` unless named), in the environment the plugin is installed in.
"""

from __future__ import annotations

import re
import sys
from importlib import metadata

from packaging.requirements import Requirement

REFUSED = re.compile(r"(^|[^L])(A?GPL|SSPL)|GNU (Affero )?General Public", re.I)


def licence(dist: metadata.Distribution) -> str:
    """The distribution's licence: its SPDX expression, else its licence
    field where it is a short name, else its licence classifiers."""
    said = dist.metadata
    expression = (said.get("License-Expression") or "").strip()
    if expression:
        return expression
    field = (said.get("License") or "").strip()
    if field and "\n" not in field and len(field) <= 80:
        return field
    classifiers = [
        each.split("::")[-1].strip()
        for each in said.get_all("Classifier") or []
        if each.startswith("License ::") and each.strip() != "License :: OSI Approved"
    ]
    return " OR ".join(classifiers)


def closure(name: str) -> list[metadata.Distribution]:
    seen: dict[str, metadata.Distribution] = {}
    todo = [name]
    while todo:
        wanted = todo.pop()
        key = re.sub(r"[-_.]+", "-", wanted).lower()
        if key in seen:
            continue
        dist = metadata.distribution(wanted)
        seen[key] = dist
        for line in dist.requires or []:
            requirement = Requirement(line)
            if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
                continue
            todo.append(requirement.name)
    return sorted(seen.values(), key=lambda d: d.metadata["Name"].lower())


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "workspace"
    refused = []
    for dist in closure(name):
        said = licence(dist)
        print(f"{dist.metadata['Name']}=={dist.version}: {said or 'UNKNOWN'}")
        choices = [each for each in re.split(r"\s+OR\s+", said.replace("(", "").replace(")", "")) if each]
        if not choices or all(REFUSED.search(each) for each in choices):
            refused.append(f"{dist.metadata['Name']}=={dist.version}: {said or 'UNKNOWN'}")
    if refused:
        print("python licences: a distribution the image ships is under a licence this fork cannot ship, "
              "or one not read:\n" + "\n".join(refused), file=sys.stderr)
        return 1
    print("python licences: none under the AGPL, the GPL or the SSPL")
    return 0


if __name__ == "__main__":
    sys.exit(main())
