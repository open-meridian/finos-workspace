"""The schema of `widgets.json` with Workspace's built-in widget types alone,
composed by upstream's own code from upstream's own kit, with no widget
plugin: what backend-api's `/app/widget-plugins/widgets-schema` answers an
organization that enabled none. backend-api is not in the image, so the
image's build writes it once, here.

upstream's module imports its database layer for the plugins it would add;
those lines are left out, and nothing that reads them is called.

Usage: python3 open-meridian/ci/widgets_schema.py OUT.json   (from the repository's root)
"""

import hashlib
import json
import sys
from pathlib import Path

MODULE = Path("backend-api/backend/api/widget_plugins/widgets_schema.py")
DATABASE = ("from sqlalchemy", "from api", "from . import")

source = "\n".join(
    line for line in MODULE.read_text().splitlines() if not line.startswith(DATABASE)
)
namespace = {"__file__": str(MODULE), "__name__": "widgets_schema"}
exec(compile(source, str(MODULE), "exec"), namespace)
kit = namespace["_kit_digest"]()
etag = hashlib.sha256(json.dumps({"kit": kit, "types": {}}, sort_keys=True).encode()).hexdigest()[:32]
schema = namespace["compose"]({}, etag, {})
Path(sys.argv[1]).write_text(json.dumps(schema, sort_keys=True))
print(f"widgets_schema: {schema['$id']}, built-in types {schema.get('x-types')}")
