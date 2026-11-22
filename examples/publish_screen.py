def publish_screen(call, document_id, size, items, metadata, source_name, png_name):
    """call accepts one JSON request and returns its successful result or raises."""
    preset = call({
        "command": "preset.create", "version": 1, "id": document_id,
        "preset": {"type": "screen", "kind": "vector", "size": size,
                   "background": {"type": "transparent"}},
    })
    document = preset["document"]
    document["items"].extend({"parent": preset["content_parent_id"], **item} for item in items)
    document["metadata"] = metadata
    source = call({"command": "document.publish", "document": document,
                   "output": {"format": "snapshot", "file_name": source_name}})
    saved = {"file_path": source_name, "sha256": source["sha256"]}
    output = {**preset["delivery"], "file_name": png_name}
    preflight = call({"command": "document.preflight", "document": saved, "output": output})
    if not preflight["ready"]:
        raise ValueError(preflight)
    png = call({"command": "document.publish", "document": saved, "output": output})
    if png["sha256"] != preflight["prepared_output"]["sha256"]:
        raise ValueError("Published PNG differs from preflight")
    return source, png
