# Move one object in an SVG

Save this artwork as `diagram.svg` in a fresh workspace. Both shapes belong
to a translated group. The edit moves the blue path and keeps its red sibling
in place.

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="48" height="32">
  <g transform="translate(3,2)">
    <path id="badge" d="M4 3H12V8H4Z" fill="#1765ab"/>
    <rect id="stop" x="30" y="2" width="5" height="4" fill="#ca4232"/>
  </g>
</svg>
```

Run this Python snippet from that directory with `inkbolt` on your PATH.

```python
import json
import subprocess
from pathlib import Path

workspace = Path.cwd().resolve()
cli = ["inkbolt", "--workspace", str(workspace), "--result-only"]

def call(command, **fields):
    reply = subprocess.run(cli, input=json.dumps(dict(command=command, **fields)),
                           text=True, stdout=subprocess.PIPE, check=True)
    return json.loads(reply.stdout)

art = call("svg.import", id="diagram", source={"kind": "file", "source_path": "diagram.svg"})
with (workspace / "import-receipt.json").open("x", encoding="utf-8") as receipt:
    json.dump(art, receipt)
item = next(row["item_id"] for row in art["mapping"] if row["source_id"] == "badge")
session = {"session_id": "diagram-edit", "response_mode": "compact"}
saved = call("session.create", **session, request_id="create", document=art["document"])
move = {"op": "transform", "id": item, "space": "world", "matrix": [1, 0, 0, 1, 6, 3]}
edited = call("session.apply", **session, expected_revision=saved["document_ref"]["revision"],
              request_id="move-badge", action={"type": "edit", "operations": [move]})
for fmt, name in [("svg", "revised.svg"), ("png", "preview.png")]:
    call("document.publish", document=edited["document_ref"],
         output={"format": fmt, "file_name": name})
```

The matrix moves the path six canvas units right and three down. The saved
receipt contains the complete import result, including the source-to-item
mapping and any reported losses. Both exports use the exact edited revision.
Open `preview.png` to review the result.
