"""Page through tools/list (nextCursor) and record every tool. Usage: python -I mcp_tools_all.py <out.json> <exe> [args...]"""
import json
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from mcp_session import Session

out, cmd = sys.argv[1], sys.argv[2:]
s = Session(cmd)
init, init_line, _ = s.initialize()
tools, pages, wire, cursor = [], 0, 0, None
while True:
    msg, line, ms = s.request("tools/list", {"cursor": cursor} if cursor else {})
    pages += 1
    wire += len(line)
    tools += msg["result"]["tools"]
    cursor = msg["result"].get("nextCursor")
    if not cursor:
        break
s.close()
summary = {"tools": len(tools), "pages": pages, "wire_bytes_all_pages": wire,
           "server": init["result"].get("serverInfo"), "protocol": init["result"].get("protocolVersion"),
           "instructions_chars": len(init["result"].get("instructions") or ""),
           "names": [t["name"] for t in tools]}
with open(out, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=1)
print(json.dumps({k: v for k, v in summary.items() if k != "names"}))
