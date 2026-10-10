"""Independent CLI checks: public XML, PNG bytes and original arithmetic fixtures."""
import base64
import binascii
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zlib
from test_cli import EXE, ROOT


def png_pixels(data):
    """Decode the bounded RGBA8 export independently, using only the standard library."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset, compressed, chunks = 8, bytearray(), {}
    while offset < len(data):
        size = struct.unpack_from(">I", data, offset)[0]
        kind, payload = data[offset+4:offset+8], data[offset+8:offset+8+size]
        assert struct.unpack_from(">I", data, offset+8+size)[0] == binascii.crc32(kind+payload)
        chunks[kind] = payload
        if kind == b"IDAT":
            compressed.extend(payload)
        offset += size + 12
    width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", chunks[b"IHDR"])
    assert (depth, color, compression, filtering, interlace) == (8, 6, 0, 0, 0)
    raw = zlib.decompress(compressed)
    stride = width*4
    assert len(raw) == height*(stride+1)
    pixels, previous = bytearray(), bytearray(stride)
    for y in range(height):
        mode = raw[y*(stride+1)]
        row = bytearray(raw[y*(stride+1)+1:(y+1)*(stride+1)])
        for i in range(stride):
            left = row[i-4] if i >= 4 else 0
            up = previous[i]
            corner = previous[i-4] if i >= 4 else 0
            if mode == 0:
                predictor = 0
            elif mode == 1:
                predictor = left
            elif mode == 2:
                predictor = up
            elif mode == 3:
                predictor = (left+up)//2
            elif mode == 4:
                p = left+up-corner
                candidates = [(abs(p-left), left), (abs(p-up), up), (abs(p-corner), corner)]
                predictor = min(enumerate(candidates), key=lambda x: (x[1][0], x[0]))[1][1]
            else:
                raise AssertionError("Unknown PNG filter")
            row[i] = (row[i]+predictor) & 255
        pixels.extend(row)
        previous = row
    return width, height, bytes(pixels), chunks


class EditingCliTests(unittest.TestCase):
    def invoke(self, request, expected=0):
        p = subprocess.run([str(EXE)], input=json.dumps(request).encode(), capture_output=True, timeout=20)
        self.assertEqual(p.returncode, expected, p.stdout.decode())
        self.assertEqual(p.stderr, b"")
        result = json.loads(p.stdout)
        self.assertEqual(result["ok"], expected == 0)
        return result["result"] if expected == 0 else result["error"]

    def vector_document(self):
        d = self.invoke(dict(command="document.create", id="fixture", kind="vector", width=16, height=12))
        items = [
            {"id": "box", "name": 'original <shape> & "label"', "content": {"type": "vector", "geometry": {"shape": "rect", "x": 2, "y": 3, "width": 8, "height": 6}, "fill": [30,100,210,255]}},
            {"id": "curve", "content": {"type": "vector", "geometry": {"shape": "path", "commands": [{"verb":"move","to":[11,1]},{"verb":"cubic","control1":[11,4],"control2":[15,4],"to":[15,1]}]}, "fill": [200,20,30,255]}}
        ]
        return self.invoke(dict(command="document.edit", document=d, expected_revision=0, operations=[dict(op="add", item=i) for i in items]))["document"]

    def test_png_dimensions_pixels_scale_metadata_and_repeatability(self):
        d = self.vector_document()
        for scale in (1, 2):
            request = dict(command="document.export", document=d, format="png", scale=scale)
            result = self.invoke(request)
            self.assertEqual(self.invoke(request), result)
            w,h,pixels,chunks = png_pixels(base64.b64decode(result["data"]))
            self.assertEqual((w,h), (16*scale,12*scale))
            self.assertIn(b"sRGB", chunks)
            self.assertEqual(struct.unpack(">IIB", chunks[b"pHYs"]), (round(96*scale/0.0254),)*2+(1,))
            for y in range(3*scale,9*scale):
                for x in range(2*scale,10*scale):
                    self.assertEqual(pixels[(y*w+x)*4:(y*w+x+1)*4], bytes([30,100,210,255]))
            self.assertEqual(pixels[:4], bytes(4))
            preview = self.invoke(dict(command="document.render", document=d, scale=scale))
            self.assertEqual(bytes.fromhex(preview["data"]), pixels)

    def test_svg_preserves_curve_numbers_escapes_names_and_shape_style(self):
        d = self.vector_document()
        result = self.invoke(dict(command="document.export", document=d, format="svg"))
        root = ET.fromstring(result["data"])
        ns = {"s": "http://www.w3.org/2000/svg"}
        self.assertEqual(root.attrib["viewBox"], "0 0 16 12")
        self.assertEqual(root.find("s:g/s:title",ns).text, 'original <shape> & "label"')
        rect = root.find("s:g/s:rect", ns)
        self.assertEqual([float(rect.attrib[a]) for a in ("x","y","width","height")], [2,3,8,6])
        self.assertEqual(rect.attrib["fill"], "#1e64d2")
        self.assertEqual(root.find(".//s:path",ns).attrib["d"].split(), ["M","11","1","C","11","4","15","4","15","1"])
        self.assertTrue(result["losses"])

    def test_pixel_alpha_source_preservation_and_png(self):
        d = self.invoke(dict(command="document.create", id="pixels", kind="raster", width=3, height=2))
        source = bytes([250,10,20,0, 90,180,45,64, 12,34,56,255])*2
        item = dict(id="source", content=dict(type="raster", width=3, height=2, rgba_hex=source.hex()))
        d = self.invoke(dict(command="document.edit",document=d,expected_revision=0,operations=[dict(op="add",item=item)]))["document"]
        saved = self.invoke(dict(command="document.export",document=d,format="snapshot"))
        reopened = self.invoke(dict(command="document.validate",document=json.loads(saved["data"])))
        self.assertEqual(reopened,d)
        self.assertEqual(bytes.fromhex(d["items"][0]["content"]["rgba_hex"]),source)
        image=self.invoke(dict(command="document.export",document=d,format="png"))
        _,_,pixels,_=png_pixels(base64.b64decode(image["data"]))
        self.assertEqual(pixels,bytes([0,0,0,0, 90,180,45,64, 12,34,56,255])*2)

    def test_failure_does_not_rewrite_input_and_valid_request_recovers(self):
        d=self.vector_document()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"original.json"
            payload=json.dumps(dict(command="document.edit",document=d,expected_revision=d["revision"],operations=[dict(op="properties",id="box",name="changed"),dict(op="remove",id="missing")])).encode()
            path.write_bytes(payload)
            p=subprocess.run([str(EXE),str(path)],capture_output=True,timeout=20)
            self.assertEqual(p.returncode,1)
            self.assertEqual(json.loads(p.stdout)["error"]["operation_index"],1)
            self.assertEqual(path.read_bytes(),payload)
        self.assertEqual(self.invoke(dict(command="document.validate",document=d)),d)
        conflict=self.invoke(dict(command="document.edit",document=d,expected_revision=0,operations=[dict(op="remove",id="box")]),1)
        self.assertEqual(conflict["code"],"REVISION_CONFLICT")

    def test_strict_nested_fields_resources_and_unsupported_exports(self):
        d=self.vector_document()
        d["items"][0]["content"]["geometry"]["unknown"]=True
        self.assertEqual(self.invoke(dict(command="document.validate",document=d),1)["code"],"INVALID_REQUEST")
        d=self.vector_document()
        self.assertEqual(self.invoke(dict(command="document.export",document=d,format="svg",scale=2),1)["code"],"UNSUPPORTED")
        d["width"]=32768
        d["height"]=32768
        self.assertEqual(self.invoke(dict(command="document.render",document=d),1)["code"],"RESOURCE_LIMIT")

    def test_f64_geometry_values_survive_json_transport_and_snapshot_exactly(self):
        values=[23.952095808383234,0.1,0.9999999999999999,32678.12345678901,-15.146750185997725]
        d=self.invoke(dict(command="document.create",id="numeric-roundtrip",kind="vector",width=10,height=10))
        items=[dict(id="precise-"+str(i),content=dict(type="vector",geometry=dict(shape="rect",x=value,y=0,width=1,height=1),fill=[0,0,0,255])) for i,value in enumerate(values)]
        d=self.invoke(dict(command="document.edit",document=d,expected_revision=0,operations=[dict(op="add",item=item) for item in items]))["document"]
        for item,value in zip(d["items"],values):self.assertEqual(float(item["content"]["geometry"]["x"]).hex(),value.hex())
        snapshot=self.invoke(dict(command="document.export",document=d,format="snapshot"))
        reopened=self.invoke(dict(command="document.validate",document=json.loads(snapshot["data"])))
        self.assertEqual(d,reopened)

    def test_example_client_exports_and_rejects_existing_destination(self):
        import sys
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/"created"
            command=[sys.executable,str(ROOT/"examples/render_example.py"),"--output-dir",str(output)]
            first=subprocess.run(command,capture_output=True,timeout=30)
            self.assertEqual(first.returncode,0,first.stderr.decode())
            original={p.name:p.read_bytes() for p in output.iterdir()}
            self.assertEqual(png_pixels(original["vector.png"])[:2],(480,240))
            self.assertEqual(png_pixels(original["raster.png"])[:2],(32,32))
            second=subprocess.run(command,capture_output=True,timeout=30)
            self.assertNotEqual(second.returncode,0)
            self.assertEqual({p.name:p.read_bytes() for p in output.iterdir()},original)


if __name__ == "__main__":
    unittest.main()
