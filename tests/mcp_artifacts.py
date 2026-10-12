"""Independent reconstruction of MCP artifact references for clients and tests."""
import base64
import hashlib


def pointer(value, path):
    for part in path.lstrip('/').split('/'):
        value = value[int(part)] if isinstance(value, list) else value[part.replace('~1','/').replace('~0','~')]
    return value


def restore(response, envelope=None):
    canonical = response['structuredContent']
    if envelope is None: envelope = canonical
    def visit(value):
        if isinstance(value, list): return [visit(v) for v in value]
        if not isinstance(value, dict): return value
        result = {k:visit(v) for k,v in value.items() if k != 'payload_ref'}
        if 'payload_ref' in value:
            ref = value['payload_ref']
            if ref['kind'] == 'content':
                block = response['content'][ref['index']]
                assert block['type'] == 'image' and block['mimeType'] == 'image/png'
                data = block['data']; raw = base64.b64decode(data, validate=True)
                assert len(raw) == ref['bytes'] and hashlib.sha256(raw).hexdigest() == ref['sha256']
            else:
                assert ref['kind'] == 'structured_content'
                data = pointer(canonical, ref['pointer'])
            result.update(encoding='base64', data=data)
        return result
    return visit(envelope)


def image_payloads(value):
    if isinstance(value, dict):
        if value.get('media_type') == 'image/png' and value.get('encoding') == 'base64': yield value['data']
        for v in value.values(): yield from image_payloads(v)
    elif isinstance(value, list):
        for v in value: yield from image_payloads(v)
