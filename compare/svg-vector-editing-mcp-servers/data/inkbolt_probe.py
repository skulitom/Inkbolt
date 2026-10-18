"""Drive Inkbolt's MCP server (core catalog) through one SVG editing task and record what happens.

Usage: python -I inkbolt_probe.py <inkbolt-exe> <path of a folder that doesn't exist yet> <fixture.svg> <out.json>

The task: import an SVG with ids, edit two elements by id in a saved session, retry the same request, preview,
publish SVG and PNG create-only, try to publish over an existing file, undo, try a stale revision, then hash the
source again. Every reply's wire size and time is kept. The fixture is hashed before the server starts.
"""
import base64
import hashlib
import json
import pathlib
import shutil
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from mcp_session import Session  # noqa: E402

exe, ws, fixture, out = sys.argv[1:5]
ws = pathlib.Path(ws)
ws.mkdir(parents=True, exist_ok=False)
src = ws / "diagram.svg"
shutil.copyfile(fixture, src)


def sha(p):
    p = pathlib.Path(p)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


LAST_IMAGES = []
record = {"exe_sha256": sha(exe), "fixture_sha256_before": sha(src), "steps": []}
s = Session([exe, "--workspace", str(ws), "mcp", "--tools", "core"])
init, _, _ = s.initialize()
record["server"] = init["result"].get("serverInfo")


def call(label, tool, args):
    msg, line, ms = s.call(tool, args)
    res = msg.get("result", {})
    payload = res.get("structuredContent")
    if payload is None:
        text = "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        try:
            payload = json.loads(text)
        except ValueError:
            payload = {"text": text[:2000]}
    is_error = bool(res.get("isError")) or ("error" in msg)
    if isinstance(payload, dict) and payload.get("ok") is False:
        is_error = True
    if isinstance(payload, dict) and payload.get("ok") is True and "result" in payload:
        payload = payload["result"]
    step = {"label": label, "tool": tool, "ms": ms, "wire_bytes": len(line), "is_error": is_error}
    images = [c for c in res.get("content", []) if c.get("type") == "image"]
    if images:
        step["image_blocks"] = [{"mime": c.get("mimeType"), "bytes": len(base64.b64decode(c["data"]))} for c in images]
        LAST_IMAGES[:] = [base64.b64decode(c["data"]) for c in images]
    if is_error:
        step["error"] = json.dumps(payload if payload else msg.get("error"))[:1500]
    record["steps"].append(step)
    return payload, is_error


def run(label, command, arguments):
    return call(label, "inkbolt_run", {"command": command, "arguments": arguments})


def item_by_id(doc, wanted):
    stack = list(doc.get("items", []))
    while stack:
        it = stack.pop()
        if it.get("id") == wanted:
            return it
        content = it.get("content") or {}
        stack.extend(content.get("items", []) or [])
        stack.extend(it.get("children", []) or [])
    return None


def ids(doc):
    found, stack = [], list(doc.get("items", []))
    while stack:
        it = stack.pop(0)
        found.append(it.get("id"))
        content = it.get("content") or {}
        stack.extend(content.get("items", []) or [])
        stack.extend(it.get("children", []) or [])
    return found


source = {"kind": "file", "source_path": "diagram.svg"}
strict, strict_err = run("svg.import strict (default policy)", "svg.import", {"id": "diagram", "source": source})
record["strict_import_refused"] = strict_err
imported, err = run("svg.import omit_and_report", "svg.import",
                    {"id": "diagram", "source": source, "unsupported": "omit_and_report"})
if err:
    # Older argument name fallback: record and stop rather than guess further.
    record["fatal"] = "svg.import with omit_and_report failed"
    json.dump(record, open(out, "w", encoding="utf-8"), indent=1)
    sys.exit(1)
doc0 = imported.get("document", imported)
record["import_report_keys"] = sorted(k for k in imported.keys() if k != "document")
record["import_omissions"] = imported.get("omissions")
record["import_losses"] = imported.get("losses")
record["import_approximations"] = imported.get("approximations")
record["ids_after_import"] = ids(doc0)

inspect, _ = call("document.inspect", "inkbolt_document_inspect", {"document": doc0})
record["inspect_item_count"] = len(json.dumps(inspect))

sid = "probe"
created, err = call("session.create", "inkbolt_session_create", {"document": doc0, "request_id": "create", "session_id": sid})


def publish(label, revision, name, fmt):
    return call(label, "inkbolt_session_publish", {"session_id": sid, "expected_revision": revision,
                                                   "output": {"output_root": "out", "file_name": name, "format": fmt}})


(ws / "out").mkdir()
publish("publish r0 svg (before any edit)", 0, "original.svg", "svg")
by_source = {m["source_id"]: m["item_id"] for m in imported.get("mapping", []) if m.get("source_id")}
record["mapping"] = by_source
OUT, IN, LINK = by_source["output"], by_source["input"], by_source["link"]
output_item = item_by_id(doc0, OUT)
input_item = item_by_id(doc0, IN)
record["output_before"] = output_item and output_item.get("content", {}).get("fill")
edit_action = {"type": "edit", "label": "recolour output, move input", "operations": [
    {"op": "vector", "id": OUT, "geometry": output_item["content"]["geometry"],
     "fill": [46, 139, 87, 255], "stroke": output_item["content"].get("stroke")},
    {"op": "transform", "id": IN, "space": "world", "matrix": [1, 0, 0, 1, 0, 10]},
]}
applied, err = call("session.apply edit", "inkbolt_session_apply",
                    {"session_id": sid, "request_id": "edit-1", "expected_revision": 0, "action": edit_action})
doc1 = applied.get("document") if isinstance(applied, dict) else None
record["revision_after_edit"] = applied.get("revision") if isinstance(applied, dict) else None
retry, err = call("session.apply same request_id retried", "inkbolt_session_apply",
                  {"session_id": sid, "request_id": "edit-1", "expected_revision": 0, "action": edit_action})
read1, _ = call("session.read after retry", "inkbolt_session_read", {"session_id": sid})
record["retry_is_error"] = err
record["head_after_retry"] = read1.get("revision", read1.get("current_revision")) if isinstance(read1, dict) else None
record["retry_receipt_equal"] = (json.dumps(retry.get("receipt"), sort_keys=True) == json.dumps(applied.get("receipt"), sort_keys=True)) if isinstance(retry, dict) else None
if doc1:
    record["output_after_edit"] = item_by_id(doc1, OUT)["content"].get("fill")

preview, err = call("document.preview revision 1", "inkbolt_document_preview", {"document": doc1})
png_b64 = None
if LAST_IMAGES:
    png_b64 = base64.b64encode(LAST_IMAGES[0]).decode()
if isinstance(preview, dict):
    for key in ("png_base64", "data", "png"):
        if isinstance(preview.get(key), str):
            png_b64 = preview[key]
            break
record["preview_keys"] = sorted(preview.keys()) if isinstance(preview, dict) else None
if png_b64:
    raw = base64.b64decode(png_b64)
    (ws / "preview-r1.png").write_bytes(raw)
    record["preview_png_bytes"] = len(raw)
    record["preview_png_size"] = [int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")]


publish("publish r1 svg", 1, "edited.svg", "svg")
publish("publish r1 png", 1, "edited.png", "png")
before_overwrite = sha(ws / "out" / "edited.svg")
_, overwrite_err = publish("publish r1 svg again to the same file", 1, "edited.svg", "svg")
record["overwrite_refused"] = overwrite_err
record["existing_output_unchanged"] = sha(ws / "out" / "edited.svg") == before_overwrite

undone, err = call("session.apply undo", "inkbolt_session_apply",
                   {"session_id": sid, "request_id": "undo-1", "expected_revision": 1, "action": {"type": "undo"}})
doc2 = undone.get("document") if isinstance(undone, dict) else None
if doc2:
    record["output_after_undo"] = item_by_id(doc2, OUT)["content"].get("fill")
    record["input_transform_after_undo"] = item_by_id(doc2, IN).get("transform")
publish("publish r2 svg", 2, "restored.svg", "svg")
record["restored_svg_equals_original_svg"] = sha(ws / "out" / "restored.svg") == sha(ws / "out" / "original.svg")
_, stale_err = call("session.apply stale expected_revision 0", "inkbolt_session_apply",
                    {"session_id": sid, "request_id": "stale-1", "expected_revision": 0,
                     "action": {"type": "edit", "operations": [{"op": "properties", "id": LINK, "visible": False}]}})
record["stale_revision_refused"] = stale_err
hist, _ = call("session.history", "inkbolt_session_history", {"session_id": sid, "limit": 16})
record["history_len"] = len(hist.get("receipts", hist.get("entries", []))) if isinstance(hist, dict) else None
s.close()

record["fixture_sha256_after"] = sha(src)
record["fixture_unchanged"] = record["fixture_sha256_after"] == record["fixture_sha256_before"]
svg_text = (ws / "out" / "edited.svg").read_text(encoding="utf-8")
record["edited_svg_keeps_source_id_attrs"] = all(f'id="{k}"' in svg_text for k in ("input", "output", "link", "arrow"))
record["edited_svg_keeps_source_ids_as_titles"] = all(f"<title>{k}</title>" in svg_text for k in ("input", "output", "link", "arrow"))
record["edited_svg_has_rect_elements"] = "<rect" in svg_text
record["outputs"] = {p.name: {"sha256": sha(p), "bytes": p.stat().st_size} for p in sorted((ws / "out").iterdir())}
record["calls"] = len(record["steps"])
record["total_wire_bytes"] = sum(st["wire_bytes"] for st in record["steps"])
record["total_ms"] = round(sum(st["ms"] for st in record["steps"]), 1)
with open(out, "w", encoding="utf-8") as f:
    json.dump(record, f, indent=1)
print(json.dumps({k: record[k] for k in record if k not in ("steps", "import_omissions")}, indent=1)[:4000])
