"""Original static fonts, text extraction, embedding restrictions and page placement."""
import copy
import itertools
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from pdf_reader import Pdf, multiply
from synthetic_font import pack, checksum
from synthetic_unicode_font import ADVANCES, rectangle, sfnt, unicode_font
from synthetic_variable_font import tables, variable_font
import test_text_cli as text_cli
import test_boards_cli as boards
from test_path_text_cli import curved, line
from test_pdf_blends_cli import poppler_rgb, pymupdf
from test_profiles_cli import builtin
import test_story_cli as story_cli


def extracted_text(data):
    # Both Poppler and Xpdf accept filenames. Xpdf's Windows CLI requires them.
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "artwork.pdf"
        output = Path(directory) / "extracted.txt"
        source.write_bytes(data)
        subprocess.run(
            ["pdftotext", "-enc", "UTF-8", str(source), str(output)],
            check=True,
            timeout=10,
        )
        return output.read_text(encoding="utf-8").rstrip("\r\n\f")


def cff_index(entries):
    if not entries:
        return b"\0\0"
    offsets = [1]
    for entry in entries:
        offsets.append(offsets[-1] + len(entry))
    return (
        pack("HB", len(entries), 2)
        + b"".join(pack("H", o) for o in offsets)
        + b"".join(entries)
    )


def cff_table():
    # One private charset. Each Type 2 charstring draws the fixture's known rectangle.
    programs = []
    for gid, advance in enumerate(ADVANCES):
        num = lambda n: b"\x1c" + pack("h", n)
        drawing = num(advance)
        if box := rectangle(gid):
            x, y, r, t = box
            drawing += num(x) + num(y) + b"\x15"
            drawing += (
                b"".join(num(n) for n in (0, t - y, r - x, 0, 0, y - t, x - r, 0))
                + b"\x05"
            )
        programs.append(drawing + b"\x0e")
    names = cff_index([b"InkboltGeometryVariable"])
    strings = cff_index([f"shape{n}".encode() for n in range(1, len(programs))])
    charset = b"\0" + b"".join(pack("H", 390 + n) for n in range(1, len(programs)))
    chars = cff_index(programs)

    # Fixed-width top dictionary operands keep the absolute offsets stable.
    def top(charset_offset, chars_offset, end):
        integer = lambda n: b"\x1d" + pack("I", n)
        return cff_index(
            [
                integer(charset_offset)
                + b"\x0f"
                + integer(chars_offset)
                + b"\x11"
                + integer(0)
                + integer(end)
                + b"\x12"
            ]
        )

    prefix = b"\x01\x00\x04\x04" + names
    start = len(prefix) + len(top(0, 0, 0)) + len(strings) + 2
    return (
        prefix
        + top(start, start + len(charset), start + len(charset) + len(chars))
        + strings
        + cff_index([])
        + charset
        + chars
    )


def font_bytes(cff=False, permissions=8, *, mark_anchor=(300, 750)):
    data = tables(unicode_font(mark_anchor=mark_anchor))
    variable = tables(variable_font())
    rights = bytearray(variable[b"OS/2"])
    struct.pack_into(">H", rights, 8, permissions)
    data.update({b"OS/2": bytes(rights), b"name": variable[b"name"]})
    if cff:
        del data[b"glyf"], data[b"loca"]
        data[b"CFF "] = cff_table()
        data[b"maxp"] = pack("IH", 0x5000, len(ADVANCES))
    return sfnt(data, 0x4F54544F if cff else 0x10000)


def cff2_font(permissions=8, variable=True):
    """An arch with a rectangular counter and a weight-dependent cubic crown."""
    def index(entries):
        return pack("I", len(entries)) + cff_index(entries)[2:] if entries else pack("I", 0)

    def operand(n):
        return b"\x1c" + pack("h", n)

    def height(value, delta):
        if variable:
            return operand(value) + operand(delta) + operand(1) + b"\x10"  # blend
        return operand(value)

    programs = []
    for gid in range(len(ADVANCES)):
        if gid in (0, 1):
            programs.append(b"")
            continue
        width = 260 + 5 * gid
        # Start at a fractional coordinate, follow the baseline and arch back.
        drawing = b"\xff" + pack("i", int(50.375*65536)) + operand(0) + b"\x15" + operand(width) + b"\x06"
        drawing += (operand(0) + height(400, 200) + operand(-width) + operand(0) +
                    operand(0) + height(-400, -200) + b"\x08")
        drawing += operand(90) + operand(40) + b"\x15"
        drawing += b"".join(operand(n) for n in (0, 60, 50, 0, 0, -60, -50, 0)) + b"\x05"
        programs.append(drawing)
    # A and B call local subroutine zero in different font dictionaries.
    locals_by_font = [index([programs[2]]), index([programs[3]])]
    programs[2] = programs[3] = operand(-107) + b"\x0a"
    chars = index(programs)
    select = bytes([0] + [int(gid == 3) for gid in range(len(programs))])
    # One positive weight region and one empty item data table for blend operands.
    region = pack("HHhhhhhh", 2, 1, 0, 16384, 16384, 0, 0, 0)
    store = pack("HIHI", 1, 12, 1, 12 + len(region)) + region + pack("HHHH", 0, 0, 1, 0)
    variations = pack("H", len(store)) + store if variable else b""
    def long(n):
        return b"\x1d" + pack("I", n)
    def top(chars_offset, fd_offset, select_offset, var_offset):
        return (long(chars_offset) + b"\x11" + long(fd_offset) + b"\x0c\x24" +
                long(select_offset) + b"\x0c\x25" +
                (long(var_offset) + b"\x18" if variable else b""))
    private = long(6) + b"\x13"  # local subroutines follow the Private DICT
    def fd(first, second):
        return index([operand(len(private)) + long(pos) + b"\x12" for pos in (first, second)])
    top_size = len(top(0, 0, 0, 0))
    start = 5 + top_size + 4
    select_offset = start + len(chars)
    fd_offset = select_offset + len(select)
    var_offset = fd_offset + len(fd(0, 0))
    first = var_offset + len(variations)
    second = first + len(private) + len(locals_by_font[0])
    cff = (pack("BBBH", 2, 0, 5, top_size) + top(start, fd_offset, select_offset, var_offset) +
           index([]) + chars + select + fd(first, second) + variations +
           private + locals_by_font[0] + private + locals_by_font[1])
    data = tables(variable_font(avar=True, hvar=True, metrics=True))
    for tag in (b"glyf", b"loca", b"gvar"):
        del data[tag]
    if not variable:
        for tag in (b"fvar", b"avar", b"HVAR", b"MVAR"):
            del data[tag]
    rights = bytearray(data[b"OS/2"])
    struct.pack_into(">H", rights, 8, permissions)
    data.update({b"CFF2": cff, b"maxp": pack("IH", 0x5000, len(ADVANCES)), b"OS/2": bytes(rights)})
    return sfnt(data, 0x4F54544F)


class SearchablePdfTests(unittest.TestCase):
    setUp = text_cli.TextCliTests.setUp
    invoke = text_cli.TextCliTests.invoke
    document = text_cli.TextCliTests.document
    edit = text_cli.TextCliTests.edit
    inspect = text_cli.TextCliTests.inspect

    def install(self, data):
        self.source.write_bytes(data)
        self.font = self.invoke(
            dict(
                command="font.import",
                source_path=str(self.source),
                license_path=str(self.license),
                store_root=str(self.store),
            )
        )

    def export(self, doc, mode=None, expected=0):
        request = dict(
            command="document.export",
            document=doc,
            font_root=str(self.store),
            format="pdf",
        )
        if mode:
            request["pdf_options"] = dict(text=mode)
        return self.invoke(request, expected)

    def test_gradient_glyphs_keep_unicode_source_fonts_and_page_space_paint(self):
        source = "A\u0301A\u0301"
        stops = [dict(offset=0, color=[250, 30, 40, 65]),
                 dict(offset=1, color=[20, 80, 222, 240])]
        axial = dict(type="linear", start=[0, 0], end=[35, 0], stops=stops)
        radial = dict(type="radial", center=[14, 20], radius=24, stops=stops)
        for cff, permissions, profile, fill in itertools.product(
            (False, True), (8, 0x108), (None, "srgb", "linear_srgb", "display_p3"), (axial, radial)
        ):
            with self.subTest(cff=cff, permissions=permissions, profile=profile, gradient=fill["type"]):
                original = font_bytes(cff, permissions, mark_anchor=(80, 160))
                self.install(original)
                doc = self.document(text=source, width=100, height=60, wrap=False,
                                    style=dict(font_id="geometry", size=36, fill=fill))
                doc.update(width=100, height=60, resolution_ppi=72)
                if profile:
                    doc["output_profile"] = builtin(profile)
                if fill is radial:
                    doc["items"][0]["transform"] = [0.95, 0.2, -0.1, 0.8, 8, 2]
                if permissions == 0x108:
                    doc["items"].insert(0, boards.BoardCliTests.rectangle(
                        self, "paper", None, "vector", 0, 0, 100, 60, [62, 110, 30, 255]))
                result = self.export(doc, "require_searchable")
                info = result["pdf"]["text_delivery"]
                self.assertEqual((info["embedded_font_programs"], info["embedded_glyphs"],
                                  info["gradient_color_glyphs"]), (1, 4, 2))
                self.assertEqual(result["pdf"]["gradient_opacity_masks"], 4)
                pdf = Pdf(result)
                self.assertEqual([s for s, _ in pdf.text_glyphs()], ["A\u0301"] * 2)
                color_fonts = [v for v in pdf.objects.values()
                               if isinstance(v, dict) and v.get("Subtype") == "Type3"]
                self.assertEqual(len(color_fonts), 2)
                for color in color_fonts:
                    self.assertEqual(len(color["Resources"]["Font"]), 1)
                    [drawing] = color["Resources"]["XObject"].values()
                    self.assertEqual(pdf.streams[drawing].count(b" sh\n"), 2)
                    l, t, r, b = pdf.get(drawing)["BBox"]
                    self.assertLess(r-l, doc["width"])
                    self.assertLess(b-t, doc["height"])
                if permissions == 0x108:
                    self.assertTrue(any(program == original for program in pdf.streams.values()))
                if shutil.which("pdftotext"):
                    self.assertEqual(extracted_text(pdf.data), source)
                control = Pdf(self.export(doc)).data
                if pymupdf:
                    solid_doc = copy.deepcopy(doc)
                    solid_doc["items"][-1]["content"]["frame"]["style"]["fill"] = [0,0,0,255]
                    normal = Pdf(self.export(solid_doc, "require_searchable")).data
                    with pymupdf.open(stream=pdf.data, filetype="pdf") as actual, pymupdf.open(
                            stream=control, filetype="pdf") as reference, pymupdf.open(
                            stream=normal, filetype="pdf") as solid:
                        self.assertEqual(actual[0].get_text().strip(), source)
                        self.assertTrue(actual[0].search_for(source))
                        self.assertEqual(actual[0].search_for(source), solid[0].search_for(source))
                        for dpi in (72, 288):
                            a, b = [p[0].get_pixmap(dpi=dpi, alpha=True).samples
                                    for p in (actual, reference)]
                            self.assertGreater(sum(b[3::4]), 0)
                            self.assertLess(abs(sum(a[3::4]) / sum(b[3::4]) - 1), 0.001)
                            self.assertLessEqual(max(abs(x-y) for x,y in zip(a,b)), 3)
                if shutil.which("pdftoppm"):
                    a,b = [poppler_rgb(data, 288, 400, 240) for data in (pdf.data, control)]
                    self.assertLessEqual(max(abs(x-y) for x,y in zip(a,b)), 3)
                self.assertEqual(self.source.read_bytes(), original)

    def test_gradient_text_on_a_curve_and_variable_glyphs_over_painted_paper(self):
        fill = dict(type="radial", center=[14, 20], radius=24,
                    stops=[dict(offset=0, color=[20, 160, 70, 190]),
                           dict(offset=1, color=[185, 20, 75, 190])])
        for source, font, frame, style in (
            ("A\u0301", font_bytes(mark_anchor=(600, 750)), dict(path=curved(start_offset=14)),
             dict(horizontal_scale=1.25, vertical_scale=0.75)),
            ("AB fi", variable_font(), {}, dict(font_variations={"geometry": {"wght":800, "wdth":150}})),
        ):
            with self.subTest(source=source):
                self.install(font)
                doc = self.document(text=source, wrap=False, **frame,
                                    style=dict(font_id="geometry", size=16, fill=fill, **style))
                doc.update(resolution_ppi=72, output_profile=builtin("linear_srgb"))
                doc["items"].insert(0, boards.BoardCliTests.rectangle(
                    self, "paper", None, "vector", 0, 0, doc["width"], doc["height"], [35, 58, 110, 255]))
                result = self.export(doc, "require_searchable")
                pdf = Pdf(result)
                self.assertEqual("".join(s for s, _ in pdf.text_glyphs()), source)
                self.assertEqual(result["pdf"]["text_delivery"]["embedded_font_programs"], 1)
                if shutil.which("pdftotext"):
                    self.assertEqual(extracted_text(pdf.data), source)
                if pymupdf:
                    with pymupdf.open(stream=pdf.data, filetype="pdf") as actual, pymupdf.open(
                            stream=Pdf(self.export(doc)).data, filetype="pdf") as outlines:
                        self.assertEqual(actual[0].get_text().strip(), source)
                        self.assertTrue(actual[0].search_for(source))
                        a, b = [p[0].get_pixmap(dpi=288, alpha=True).samples for p in (actual, outlines)]
                        self.assertLessEqual(max(abs(x-y) for x,y in zip(a,b)), 3)

    def test_restricted_gradient_text_refuses_strict_publication(self):
        self.install(font_bytes(permissions=2))
        doc = self.document(text="AA", style=dict(font_id="geometry", size=18, fill=dict(
            type="linear", start=[0, 0], end=[25, 0], stops=[
                dict(offset=0, color=[255, 0, 0, 255]), dict(offset=1, color=[0, 0, 255, 255])])))
        fallback = self.export(doc, "searchable")
        self.assertEqual(fallback["pdf"]["text_delivery"]["outlined_items_by_reason"], {"restricted_embedding": 1})
        self.assertEqual(Pdf(fallback).data, Pdf(self.export(doc)).data)
        error = self.invoke(dict(command="document.publish", document=doc,
                                 resources=dict(font_root=str(self.store)),
                                 output=dict(output_root=str(self.directory), file_name="gradient.pdf",
                                             format="pdf", pdf_options=dict(text="require_searchable"))), 1)
        self.assertIn("restricted_embedding", error["message"])
        self.assertFalse((self.directory / "gradient.pdf").exists())

    def test_variable_instances_embed_their_own_outlines_advances_and_unicode(self):
        from test_font_controls_cli import deformation

        original = variable_font(avar=True, hvar=True, metrics=True)
        self.install(original)
        doc = self.document(text="AA", wrap=False)
        doc.update(width=120, height=110, resolution_ppi=72)
        label = doc["items"][0]
        label["content"]["frame"]["style"]["size"] = 20
        instances = [(400, 100), (650, 150), (900, 200), (650, 150)]
        edits = []
        for i, (weight, width) in enumerate(instances[1:], 1):
            item = copy.deepcopy(label)
            item.update(id=f"instance-{i}", transform=[1, 0, 0, 1, 0, 25*i])
            item["content"]["frame"]["style"]["font_variations"] = {
                "geometry": dict(wght=weight, wdth=width)
            }
            edits.append(dict(op="add", item=item))
        doc = self.edit(doc, edits)
        result = self.export(doc, "require_searchable")
        self.assertEqual(result["pdf"]["text_delivery"]["embedded_font_programs"], 3)
        pdf = Pdf(result)
        self.assertEqual([s for s, _ in pdf.text_glyphs()], ["A"]*8)
        metrics = {}
        for font in pdf.objects.values():
            if not isinstance(font, dict) or font.get("Subtype") != "CIDFontType2":
                continue
            desc = pdf.objects[font["FontDescriptor"]]
            program = pdf.streams[desc["FontFile2"]]
            self.assertEqual(checksum(program), 0xB1B0AFBA)
            data = tables(program)
            self.assertFalse({b"gvar", b"fvar", b"avar", b"HVAR", b"MVAR"} & data.keys())
            self.assertEqual(data[b"OS/2"][8:10], tables(original)[b"OS/2"][8:10])
            self.assertEqual(struct.unpack_from(">H", data[b"maxp"], 4)[0], 2)
            # Read A from its embedded CID mapping and glyph location table.
            gid = struct.unpack_from(">H", pdf.streams[font["CIDToGIDMap"]], 2)[0]
            long_offsets = struct.unpack_from(">h", data[b"head"], 50)[0]
            if long_offsets:
                offset = struct.unpack_from(">I", data[b"loca"], gid * 4)[0]
            else:
                offset = 2 * struct.unpack_from(">H", data[b"loca"], gid * 2)[0]
            box = struct.unpack_from(">hhhh", data[b"glyf"], offset + 2)
            self.assertEqual(tuple(desc["FontBBox"]), box)
            self.assertEqual(struct.unpack_from(">hhhh", data[b"head"], 36), box)
            advance = font["W"][1][0]
            count = struct.unpack_from(">H", data[b"hhea"], 34)[0]
            self.assertEqual(struct.unpack_from(">H", data[b"hmtx"], min(gid, count-1)*4)[0], advance)
            self.assertEqual(struct.unpack_from(">hh", data[b"OS/2"], 68), (desc["Ascent"], desc["Descent"]))
            self.assertEqual(struct.unpack_from(">hhh", data[b"hhea"], 12), (50, advance-box[2], box[2]))
            weight_class, width_class = struct.unpack_from(">HH", data[b"OS/2"], 4)
            metrics[advance] = (box, desc["Ascent"], desc["Descent"], weight_class, width_class)
        for weight, width in set(instances):
            dx, dy, w, _ = deformation(weight, width, remap=True)
            self.assertEqual(metrics[600+dx], (
                (50, 0, 170+dx, 410+dy), 1000+200*w, -200-100*w, weight, {100: 5, 150: 8, 200: 9}[width],
            ))
        if shutil.which("pdftotext"):
            self.assertEqual(extracted_text(pdf.data).split(), ["AA"]*4)
        if pymupdf:
            with pymupdf.open(stream=pdf.data, filetype="pdf") as actual, pymupdf.open(
                stream=Pdf(self.export(doc)).data, filetype="pdf"
            ) as outlines:
                self.assertEqual(actual[0].get_text().split(), ["AA"]*4)
                self.assert_cluster_raster(actual[0].get_pixmap(dpi=288, alpha=True),
                                           outlines[0].get_pixmap(dpi=288, alpha=True), 0.005)
        self.assertEqual(self.source.read_bytes(), original)

    def test_variable_font_that_requires_whole_embedding_keeps_its_rights(self):
        data = tables(variable_font())
        rights = bytearray(data[b"OS/2"])
        struct.pack_into(">H", rights, 8, 0x108)
        data[b"OS/2"] = bytes(rights)
        original = sfnt(data)
        self.install(original)
        doc = self.document(text="A")
        fallback = self.export(doc, "searchable")
        self.assertEqual(fallback["pdf"]["text_delivery"]["outlined_items_by_reason"], {"variable_font": 1})
        self.assertEqual(Pdf(fallback).data, Pdf(self.export(doc)).data)
        self.assertIn("variable_font", self.export(doc, "require_searchable", 1)["message"])
        self.assertEqual(self.source.read_bytes(), original)

    def test_cff2_curves_and_counters_survive_searchable_pdf_instances(self):
        for variable, weight, height, advance in [(False, 400, 400, 600),
                (True, 400, 400, 600), (True, 650, 550, 750), (True, 900, 600, 800)]:
            with self.subTest(variable=variable, weight=weight):
                original = cff2_font(variable=variable)
                self.install(original)
                style = dict(font_id="geometry", size=40, fill=[20, 80, 135, 255])
                if variable:
                    style["font_variations"] = {"geometry": {"wght": weight}}
                doc = self.document(text="AB", width=100, height=75, wrap=False, style=style)
                doc.update(resolution_ppi=72, width=100, height=75)
                layout = self.inspect(doc, include_outlines=True)["layout"]
                glyph = layout["glyphs"][0]
                x, y = glyph["origin"]
                curve = next(c for c in layout["paths"][0]["geometry"]["commands"] if c["verb"] == "cubic")
                self.assertAlmostEqual(curve["control1"][0], x + 320.375 * .04)
                self.assertAlmostEqual(curve["control2"][0], x + 50.375 * .04)
                self.assertEqual(curve["control1"][1], y - height * .04)
                self.assertEqual(curve["control2"][1], y - height * .04)
                result = self.export(doc, "require_searchable")
                pdf = Pdf(result)
                self.assertEqual(result["pdf"]["text_delivery"]["embedded_font_programs"], 1)
                font = next(v for v in pdf.objects.values() if isinstance(v, dict) and v.get("Subtype") == "CIDFontType2")
                self.assertEqual(font["W"], [1, [advance], 2, [advance + 50]])
                descriptor = pdf.get(font["FontDescriptor"])
                self.assertEqual(descriptor["FontBBox"], [50, 0, 325, int(.75 * height + .5)])
                embedded = pdf.streams[descriptor["FontFile2"]]
                data = tables(embedded)
                self.assertEqual(checksum(embedded), 0xB1B0AFBA)
                self.assertEqual(data[b"OS/2"][8:10], pack("H", 8))
                self.assertEqual(struct.unpack_from(">H", data[b"maxp"], 4)[0], 3)
                self.assertIn(b"glyf", data)
                self.assertFalse({b"CFF2", b"fvar", b"HVAR"} & data.keys())
                self.assertEqual([s for s, _ in pdf.text_glyphs()], ["A", "B"])
                if shutil.which("pdftotext"):
                    self.assertEqual(extracted_text(pdf.data), "AB")
                if pymupdf:
                    with pymupdf.open(stream=pdf.data, filetype="pdf") as actual, pymupdf.open(
                        stream=Pdf(self.export(doc)).data, filetype="pdf"
                    ) as reference:
                        self.assertEqual(actual[0].get_text().strip(), "AB")
                        a, b = [page[0].get_pixmap(dpi=288, alpha=True) for page in (actual, reference)]
                        self.assert_cluster_raster(a, b, 0.01)
                        # The counter at (160, 70) stays clear. Ink surrounds it.
                        for fx, fy, alpha in [(160, 70, 0), (110, 70, 255), (160, 170, 255)]:
                            self.assertEqual(a.pixel(round(4*(x+fx*.04)), round(4*(y-fy*.04)))[3], alpha)
                self.assertEqual(self.source.read_bytes(), original)

    def test_cff2_embedding_obeys_font_rights_before_publication(self):
        for variable, permissions, reason in [(True, 0x108, "variable_font"),
                (False, 0x108, "whole_cff2_font"), (True, 2, "restricted_embedding")]:
            self.install(cff2_font(permissions, variable))
            doc = self.document(text="AB fi", wrap=False)
            fallback = self.export(doc, "searchable")
            self.assertEqual(fallback["pdf"]["text_delivery"]["outlined_items_by_reason"], {reason: 1})
            self.assertEqual(Pdf(fallback).data, Pdf(self.export(doc)).data)
            result = self.invoke(dict(command="document.publish", document=doc, resources=dict(font_root=str(self.store)),
                                      output=dict(format="pdf", file_name="letters.pdf", output_root=str(self.directory),
                                                  pdf_options=dict(text="require_searchable"))), 1)
            self.assertIn(reason, result["message"])
            self.assertFalse((self.directory / "letters.pdf").exists())

    def test_cff2_ligature_maps_to_its_word_without_duplicate_replacement_text(self):
        self.install(cff2_font())
        for fill in ([20, 80, 135, 255], dict(type="linear", start=[0, 0], end=[90, 0],
                stops=[dict(offset=0, color=[0, 0, 0, 255]), dict(offset=1, color=[95, 20, 80, 255])])):
            doc = self.document(text="AB fi", wrap=False, width=120,
                                style=dict(font_id="geometry", size=25, fill=fill))
            pdf = Pdf(self.export(doc, "require_searchable"))
            self.assertEqual([s for s, _ in pdf.text_glyphs()], ["A", "B", " ", "fi"])
            self.assertFalse(any(b"/ActualText" in content for content in pdf.streams.values()))
            if shutil.which("pdftotext"):
                self.assertEqual(extracted_text(pdf.data), "AB fi")

    def test_variable_advances_from_phantom_points_or_metrics_only_font(self):
        for only_metrics in (False, True):
            with self.subTest(only_metrics=only_metrics):
                data = tables(variable_font(hvar=only_metrics))
                if only_metrics:
                    del data[b"gvar"]
                self.install(sfnt(data))
                doc = self.document(text="AA", style=dict(font_id="geometry", size=20, fill=[25,100,200,255],
                                    font_variations={"geometry": {"wght": 900, "wdth": 200}}))
                pdf = Pdf(self.export(doc, "require_searchable"))
                font = next(f for f in pdf.objects.values() if isinstance(f, dict) and f.get("Subtype") == "CIDFontType2")
                self.assertEqual(font["W"], [1, [1200]])
                desc = pdf.objects[font["FontDescriptor"]]
                self.assertEqual(desc["FontBBox"], [50, 0, 170, 410] if only_metrics else [50, 0, 770, 510])

    def test_subset_and_whole_programs_retain_glyphs_rights_and_source_text(self):
        for cff in (False, True):
            for whole in (False, True):
                with self.subTest(cff=cff, whole=whole):
                    original = font_bytes(cff, 0x108 if whole else 8)
                    self.install(original)
                    source = "AB fi é"
                    doc = self.document(text=source, wrap=False)
                    glyphs = self.inspect(doc)["layout"]["glyphs"]
                    result = self.export(doc, "require_searchable")
                    receipt = result["pdf"]["text_delivery"]
                    self.assertEqual(result["pdf"]["text"], "searchable")
                    self.assertEqual(receipt["embedded_glyphs"], len(glyphs))
                    self.assertEqual(receipt["embedded_font_programs"], 1)
                    self.assertEqual(receipt["outlined_items_by_reason"], {})
                    pdf = Pdf(result)
                    descriptor = next(
                        v
                        for v in pdf.objects.values()
                        if isinstance(v, dict) and v.get("Type") == "FontDescriptor"
                    )
                    program = pdf.streams[
                        descriptor["FontFile3" if cff else "FontFile2"]
                    ]
                    self.assertEqual(checksum(program), 0xB1B0AFBA)
                    self.assertEqual(
                        tables(program)[b"OS/2"], tables(original)[b"OS/2"]
                    )
                    n = struct.unpack_from(">H", tables(program)[b"maxp"], 4)[0]
                    if whole:
                        self.assertEqual(program, original)
                    else:
                        self.assertLess(n, len(ADVANCES))
                    extracted = pdf.text_glyphs()
                    self.assertEqual("".join(s for s, _ in extracted), source)
                    self.assertEqual(len(extracted), len(glyphs))
                    for (_, matrix), glyph in zip(extracted, glyphs):
                        self.assertAlmostEqual(
                            matrix[4], glyph["origin"][0] * 72 / doc["resolution_ppi"]
                        )
                        self.assertAlmostEqual(
                            matrix[5],
                            (doc["height"] - glyph["origin"][1])
                            * 72
                            / doc["resolution_ppi"],
                        )
                    default = Pdf(self.export(doc))
                    self.assertEqual(
                        default.data, Pdf(self.export(doc, "outlines")).data
                    )
                    self.assertFalse(default.text_glyphs())

    def test_restrictions_fall_back_or_fail_before_publication(self):
        for flag, reason in [
            (2, "restricted_embedding"),
            (4, "read_only_embedding_required"),
            (0x208, "bitmap_only_embedding"),
        ]:
            with self.subTest(flag=flag):
                self.install(font_bytes(permissions=flag))
                doc = self.document()
                result = self.export(doc, "searchable")
                self.assertEqual(result["pdf"]["text"], "vector_outlines")
                self.assertEqual(
                    result["pdf"]["text_delivery"]["outlined_items_by_reason"],
                    {reason: 1},
                )
                self.assertEqual(Pdf(result).data, Pdf(self.export(doc)).data)
                err = self.export(doc, "require_searchable", 1)
                self.assertEqual(err["code"], "UNSUPPORTED")
                self.assertIn(reason, err["message"])
                target = self.directory / "restricted.pdf"
                error = self.invoke(
                    dict(
                        command="document.publish",
                        document=doc,
                        resources=dict(font_root=str(self.store)),
                        output=dict(
                            output_root=str(self.directory),
                            file_name=target.name,
                            format="pdf",
                            pdf_options=dict(text="require_searchable"),
                        ),
                    ),
                    1,
                )
                self.assertEqual(error["code"], "UNSUPPORTED")
                self.assertFalse(target.exists())

    def test_searchable_rtl_lines_keep_reading_order_and_word_positions(self):
        gradient = dict(type="linear", start=[0, 0], end=[95, 0], stops=[
            dict(offset=0, color=[25, 185, 10, 160]), dict(offset=1, color=[220, 20, 75, 210])])
        for cff, permissions, source, paint in itertools.product(
                (False, True), (8, 0x108), ("אב באב", "بت تبت"), ([20, 110, 90, 177], gradient)):
            with self.subTest(cff=cff, permissions=permissions, source=source, gradient=paint==gradient):
                self.install(font_bytes(cff, permissions))
                doc = self.document(text=source, width=125, height=40, wrap=False, bidi="unicode",
                                    direction="auto", style=dict(font_id="geometry", size=16, fill=paint))
                doc.update(width=125, height=40, resolution_ppi=72)
                glyphs = self.inspect(doc)["layout"]["glyphs"]
                result = self.export(doc, "require_searchable")
                self.assertEqual(result["pdf"]["text"], "searchable")
                pdf = Pdf(result)
                mapped = pdf.text_glyphs()
                self.assertEqual([c for c, _ in mapped], list(reversed(source)))
                for (c, matrix), glyph in zip(mapped, glyphs):
                    self.assertAlmostEqual(matrix[4], glyph["origin"][0])
                    self.assertAlmostEqual(matrix[5], doc["height"] - glyph["origin"][1])
                    if paint == gradient and c != " ":
                        self.assertAlmostEqual(matrix[0], glyph["advance"])
                if paint == gradient:
                    color_fonts = [obj for obj in pdf.objects.values()
                                   if isinstance(obj, dict) and obj.get("Subtype") == "Type3"]
                    self.assertEqual(len(color_fonts), len(source.replace(" ", "")))
                    self.assertTrue(all(f["Widths"] == [1000] for f in color_fonts))
                self.assertTrue(any(isinstance(obj, dict) and obj.get("TK") is False
                                    for obj in pdf.objects.values()))
                self.assertFalse(any(b"/ActualText" in s for s in pdf.streams.values()))
                if shutil.which("pdftotext"):
                    # Command-line readers can wrap RTL output in bidi display controls.
                    self.assertEqual(re.sub("[\u202a-\u202e]", "", extracted_text(pdf.data)), source)
                if pymupdf:
                    with pymupdf.open(stream=pdf.data, filetype="pdf") as opened:
                        page = opened[0]
                        self.assertEqual(page.get_text().rstrip("\r\n"), source)
                        self.assertTrue(page.search_for(source))
                        for word in re.finditer(r"\S+", source):
                            placed = [g for g in glyphs if word.start() <= g["start"] < word.end()]
                            left = min(g["origin"][0] for g in placed)
                            right = max(g["origin"][0] + g["advance"] for g in placed)
                            hits = [h for h in page.search_for(word.group())
                                    if h.x0 >= left - 0.02 and h.x1 <= right + 0.02]
                            self.assertTrue(hits)
                            self.assertAlmostEqual(min(h.x0 for h in hits), left, delta=.02)
                            self.assertAlmostEqual(max(h.x1 for h in hits), right, delta=.02)
                            box = pymupdf.Rect(left + .05, min(h.y0 for h in hits),
                                               right - .05, max(h.y1 for h in hits))
                            self.assertEqual(page.get_textbox(box), word.group())

    def test_separate_rtl_and_ltr_lines_preserve_their_own_reading_order(self):
        self.install(font_bytes())
        for source in ("אב\nبت", "AB\nאב", "אב\nAB"):
            with self.subTest(source=source):
                doc = self.document(text=source, wrap=False, direction="auto", bidi="unicode")
                pdf = Pdf(self.export(doc, "require_searchable"))
                self.assertEqual("".join(c for c, _ in pdf.text_glyphs()),
                                 "".join(s if s=="AB" else s[::-1] for s in source.splitlines()))
                if pymupdf:
                    with pymupdf.open(stream=pdf.data, filetype="pdf") as opened:
                        self.assertEqual(opened[0].get_text().rstrip("\r\n"), source)

    def test_overlapping_rtl_glyphs_keep_separate_translucent_paints(self):
        def overhang(gid):
            return (0, 0, 1100, 600) if gid in (17, 18) else rectangle(gid)

        with patch("synthetic_unicode_font.rectangle", overhang):
            self.install(font_bytes())
        red = dict(font_id="geometry", size=20, fill=[250, 50, 0, 128])
        blue = dict(font_id="geometry", size=20, fill=[20, 80, 240, 128])
        doc = self.document(text="אב", bidi="unicode", direction="auto", wrap=False,
                            style=red, ranges=[dict(start=0, end=1, style=blue)])
        doc["resolution_ppi"] = 72
        pdf = Pdf(self.export(doc, "require_searchable"))
        self.assertEqual([s for s, _ in pdf.text_glyphs()], ["ב", "א"])
        if pymupdf:
            with pymupdf.open(stream=pdf.data, filetype="pdf") as actual, pymupdf.open(
                    stream=Pdf(self.export(doc)).data, filetype="pdf") as control:
                self.assertEqual(actual[0].get_text().strip(), "אב")
                pixels = actual[0].get_pixmap(alpha=True)
                outlines = control[0].get_pixmap(alpha=True)
                for x in (5, 17, 28):
                    self.assertEqual(pixels.pixel(x, 14), outlines.pixel(x, 14))
                # The two half-opacity glyphs overlap from x=14 to x=22.
                self.assertAlmostEqual(pixels.pixel(17, 14)[3], 191, delta=2)
                self.assertGreater(pixels.pixel(17, 14)[2], pixels.pixel(17, 14)[0])

    def test_complex_rtl_falls_back_for_the_whole_item(self):
        self.install(font_bytes())
        for source,extra,transform,reason in [
            ("א\u0301ב", {}, None, "right_to_left_source"),
            ("אב באב,", {}, None, "right_to_left_source"),
            ("אב  באב", {}, None, "right_to_left_source"),
            ("אב\nA بت", {}, None, "right_to_left_run"),
            ("\u202bאב\u202c", {}, None, "right_to_left_source"),
            ("אב באב", dict(path=curved()), None, "right_to_left_geometry"),
            ("אב באב", {}, [-1,0,0,1,65,0], "right_to_left_geometry"),
            ("אב באב", {}, [0,1,-1,0,65,0], "right_to_left_geometry"),
            ("אב באב", dict(style=dict(font_id="geometry", size=16, fill=[0,0,0,255], tracking=3)),
             None, "right_to_left_geometry"),
        ]:
            with self.subTest(source=source, reason=reason):
                doc = self.document(text=source, width=140, wrap=False, direction="auto", bidi="unicode", **extra)
                if transform:
                    doc["items"][0]["transform"] = transform
                result = self.export(doc, "searchable")
                self.assertEqual(result["pdf"]["text_delivery"]["outlined_items_by_reason"], {reason: 1})
                self.assertEqual(Pdf(result).data, Pdf(self.export(doc)).data)
                self.assertIn(reason, self.export(doc, "require_searchable", 1)["message"])

    def test_rtl_source_respects_searchable_delivery_in_both_layout_modes(self):
        self.install(font_bytes())
        for source in ("A אב", "A بت"):
            for layout, reason in (
                ({}, "right_to_left_source"),
                (dict(bidi="unicode", direction="auto"), "right_to_left_run"),
            ):
                with self.subTest(source=source, layout=layout):
                    doc = self.document(text=source, wrap=False, **layout)
                    result = self.export(doc, "searchable")
                    self.assertEqual(result["pdf"]["text"], "vector_outlines")
                    self.assertEqual(
                        result["pdf"]["text_delivery"]["outlined_items_by_reason"],
                        {reason: 1},
                    )
                    self.assertEqual(Pdf(result).data, Pdf(self.export(doc)).data)
                    self.assertIn(
                        reason, self.export(doc, "require_searchable", 1)["message"]
                    )

    def test_mixed_items_share_the_font_and_report_only_the_outlined_item(self):
        self.install(font_bytes())
        doc = self.document(text="fi")
        label = doc["items"][0]
        second = copy.deepcopy(label)
        second.update(id="shifted", transform=[1, 0, 0, 1, 32, 4])
        self.install(font_bytes(permissions=2))
        third = copy.deepcopy(label)
        third.update(id="restricted", transform=[1, 0, 0, 1, 0, 24])
        third["content"]["frame"]["style"]["font_id"] = "restricted-font"
        doc = self.edit(
            doc,
            [
                dict(op="font_put", id="restricted-font", font=self.font),
                dict(op="add", item=second),
                dict(op="add", item=third),
            ],
        )
        result = self.export(doc, "searchable")
        self.assertEqual(result["pdf"]["text"], "mixed_searchable_and_outlines")
        self.assertEqual(
            result["pdf"]["text_delivery"],
            dict(
                requested="searchable",
                embedded_font_programs=1,
                embedded_glyphs=2,
                outlined_items_by_reason={"restricted_embedding": 1},
            ),
        )
        glyphs = Pdf(result).text_glyphs()
        self.assertEqual([source for source, _ in glyphs], ["fi", "fi"])
        self.assertAlmostEqual(
            glyphs[1][1][4] - glyphs[0][1][4], 32 * 72 / doc["resolution_ppi"]
        )
        self.assertAlmostEqual(
            glyphs[1][1][5] - glyphs[0][1][5], -4 * 72 / doc["resolution_ppi"]
        )

    def test_combining_marks_use_the_shaped_glyphs_and_copy_once(self):
        source = "A\u0301Afi A\u0301"
        for cff in (False, True):
            for whole in (False, True):
                with self.subTest(cff=cff, whole=whole):
                    self.install(font_bytes(cff, 0x108 if whole else 8))
                    doc = self.document(text=source, wrap=False)
                    result = self.export(doc, "require_searchable")
                    pdf = Pdf(result)
                    clusters = [
                        v
                        for v in pdf.objects.values()
                        if isinstance(v, dict) and v.get("Subtype") == "Type3"
                    ]
                    self.assertEqual(len(clusters), 1)
                    self.assertEqual(
                        [v for v, _ in pdf.text_glyphs()],
                        ["A\u0301", "A", "fi", " ", "A\u0301"],
                    )
                    self.assertEqual(
                        result["pdf"]["text_delivery"]["embedded_glyphs"], 7
                    )
                    cluster = clusters[0]
                    procedure = pdf.streams[cluster["CharProcs"]["Cluster"]].decode()
                    self.assertEqual(cluster["Widths"], [600])
                    self.assertIn("1 0 0 1 300 750 Tm", procedure)
                    self.assertEqual(procedure.count(" Tj"), 2)
                    self.assertEqual(len(cluster["Resources"]["Font"]), 1)
                    if pymupdf:
                        with pymupdf.open(stream=pdf.data, filetype="pdf") as parsed:
                            self.assertEqual(
                                parsed[0].get_text().rstrip("\r\n"), source
                            )
                    if shutil.which("pdftotext"):
                        self.assertEqual(extracted_text(pdf.data), source)

    @unittest.skipUnless(pymupdf, "MuPDF renders the colored combining clusters")
    def test_scaled_combining_marks_match_outline_coverage_and_fill(self):
        self.install(font_bytes())
        doc = self.document(
            text="A\u0301Afi A\u0301",
            width=120,
            height=60,
            wrap=False,
            style=dict(
                font_id="geometry",
                size=32,
                horizontal_scale=1.25,
                vertical_scale=0.8,
                fill=[25, 100, 200, 255],
            ),
        )
        doc.update(width=120, height=60, resolution_ppi=72)
        actual = Pdf(self.export(doc, "require_searchable")).data
        outlined = Pdf(self.export(doc)).data
        with pymupdf.open(stream=actual, filetype="pdf") as f, pymupdf.open(
            stream=outlined, filetype="pdf"
        ) as r:
            a = f[0].get_pixmap(dpi=288, alpha=True)
            b = r[0].get_pixmap(dpi=288, alpha=True)
            self.assert_cluster_raster(a, b, 0.001)

    def assert_cluster_raster(self, actual, reference, max_area_error):
        self.assertEqual(actual.irect, reference.irect)
        rgba, ref = actual.samples, reference.samples
        alpha, coverage = rgba[3::4], ref[3::4]
        self.assertGreater(sum(coverage), 0)
        self.assertLess(abs(sum(alpha) - sum(coverage)) / sum(coverage), max_area_error)
        # Glyph and outline scan conversion can place an edge one device pixel apart.
        for i, (v, w) in enumerate(zip(alpha, coverage)):
            if v == w == 255:
                self.assertEqual(rgba[4 * i : 4 * i + 3], ref[4 * i : 4 * i + 3])
            elif v != w:
                x, y = i % actual.width, i // actual.width
                neighbors = [
                    yy * actual.width + xx
                    for yy in range(max(0, y - 1), min(actual.height, y + 2))
                    for xx in range(max(0, x - 1), min(actual.width, x + 2))
                ]
                for value, other in ((v, coverage), (w, alpha)):
                    around = [other[j] for j in neighbors]
                    self.assertLessEqual(min(around), value)
                    self.assertGreaterEqual(max(around), value)

    def test_translucent_mark_cluster_keeps_per_glyph_paint(self):
        self.install(font_bytes(mark_anchor=(80, 160)))
        source = "A\u0301A\u0301"
        byte_fill = [148, 38, 82, 127]
        for fill, alpha, profile in (
            (byte_fill, 127 / 255, None),
            (byte_fill, 127 / 255, "srgb"),
            (byte_fill, 127 / 255, "linear_srgb"),
            (byte_fill, 127 / 255, "display_p3"),
            ({"rgba": [0.12, 0.38, 0.78, 0.5]}, 0.5, None),
            ({"rgba": [0.12, 0.38, 0.78, 0.5]}, 0.5, "linear_srgb"),
            ({"rgba": [0.12, 0.38, 0.78, 0.9999]}, 0.9999, None),
        ):
            with self.subTest(fill=fill, profile=profile):
                doc = self.document(
                    text=source, width=100, height=60, wrap=False,
                    style=dict(font_id="geometry", size=36, fill=fill),
                )
                doc.update(width=100, height=60, resolution_ppi=72)
                if profile:
                    doc["output_profile"] = builtin(profile)
                result = self.export(doc, "require_searchable")
                pdf = Pdf(result)
                self.assertEqual(result["pdf"]["text_delivery"]["embedded_glyphs"], 4)
                self.assertEqual([s for s, _ in pdf.text_glyphs()], ["A\u0301"] * 2)
                cluster, = [v for v in pdf.objects.values()
                            if isinstance(v, dict) and v.get("Subtype") == "Type3"]
                body = pdf.streams[cluster["CharProcs"]["Cluster"]]
                self.assertTrue(body.startswith(b"600 0 d0\n"))
                if profile:
                    form, = cluster["Resources"]["XObject"].values()
                    self.assertIn(f"/R{form} Do".encode(), body)
                    rgb = pdf.pages[0]["Resources"]["ColorSpace"]["DefaultRGB"]
                    self.assertEqual(cluster["Resources"]["ColorSpace"]["DefaultRGB"], rgb)
                    self.assertEqual(pdf.objects[form]["Resources"]["ColorSpace"]["DefaultRGB"], rgb)
                    body = pdf.streams[form]
                self.assertEqual(body.count(b" Tj"), 2)
                if shutil.which("pdftotext"):
                    self.assertEqual(extracted_text(pdf.data), source)
                outlined = Pdf(self.export(doc)).data
                base, mark = [glyph["ink_bounds"] for glyph in self.inspect(doc)["layout"]["glyphs"][:2]]
                x = (max(base[0], mark[0]) + min(base[2], mark[2])) / 2
                # Sample the base below the mark, then deep inside their overlap.
                ys = ((mark[3] + base[3]) / 2, (max(base[1], mark[1]) + min(base[3], mark[3])) / 2)
                points = [(int(4 * x), int(4 * y)) for y in ys]
                if pymupdf:
                    with pymupdf.open(stream=pdf.data, filetype="pdf") as f, pymupdf.open(stream=outlined, filetype="pdf") as r:
                        self.assertEqual(f[0].get_text().rstrip("\r\n"), source)
                        actual = f[0].get_pixmap(dpi=288, alpha=True)
                        reference = r[0].get_pixmap(dpi=288, alpha=True)
                        base_pixel, overlap_pixel = [actual.pixel(*xy) for xy in points]
                        self.assertEqual([base_pixel, overlap_pixel], [reference.pixel(*xy) for xy in points])
                        self.assertAlmostEqual(base_pixel[3], alpha * 255, delta=2)
                        # Compose the reader's quantized single-layer alpha twice.
                        overlap_alpha = 255 * (1 - (1 - base_pixel[3] / 255) ** 2)
                        self.assertAlmostEqual(overlap_pixel[3], overlap_alpha, delta=2)
                if shutil.which("pdftoppm"):
                    rgb = poppler_rgb(pdf.data, 288, 400, 240)
                    expected = poppler_rgb(outlined, 288, 400, 240)
                    for x, y in points:
                        i = 3 * (400 * y + x)
                        self.assertEqual(rgb[i:i + 3], expected[i:i + 3])

    def test_cluster_paints_share_only_matching_page_resources_and_require_paper_for_marks(self):
        self.install(font_bytes(mark_anchor=(80, 160)))
        doc = self.document(text="A\u0301")
        template, = doc["items"]
        doc["items"] = []
        red, blue = [160, 30, 14, 128], [5, 50, 100, 64]
        for board_id, fills in (("paper", [red, blue, red]), ("clear", [red])):
            board = boards.BoardCliTests.board(self, board_id, 60, 40)
            if board_id == "paper":
                board["content"]["frame"]["background"] = [255, 255, 255, 255]
            doc["items"].append(board)
            for index, fill in enumerate(fills):
                label = copy.deepcopy(template)
                label.update(id=f"{board_id}-{index}", parent=board_id, transform=[1, 0, 0, 1, 15 * index, 0])
                label["content"]["frame"]["style"]["fill"] = fill
                doc["items"].append(label)
        options = dict(text="require_searchable", artboards=dict(type="ids", ids=["paper", "clear"]))
        request = dict(command="document.export", document=doc, font_root=str(self.store),
                       format="pdf", pdf_options=options)
        pdf = Pdf(self.invoke(request))
        self.assertEqual([[s for s, _ in pdf.text_glyphs(i)] for i in range(2)],
                         [["A\u0301"] * 3, ["A\u0301"]])
        clusters = [v for v in pdf.objects.values() if isinstance(v, dict) and v.get("Subtype") == "Type3"]
        self.assertEqual(len(clusters), 3)  # two paints on the first page, one on the second
        options["marks"] = {}
        options["artboards"]["ids"] = ["paper"]
        self.assertEqual(self.invoke(request)["pages"][0]["opaque_rgb_paper"]["item_id"], "paper")
        options["artboards"]["ids"].append("clear")
        self.assertIn("opaque paper", self.invoke(request, 1)["message"])
        options["matte"] = [255, 255, 255]
        self.assertEqual(len(self.invoke(request)["pages"]), 2)

    def test_linked_story_uses_each_paragraphs_source(self):
        self.install(font_bytes())
        doc = story_cli.StoryTests.document(
            self,
            [story_cli.StoryTests.paragraph(self, text) for text in ("fi", "éB")],
            [
                dict(id="first", width=48, height=12),
                dict(id="second", width=48, height=24),
            ],
        )
        glyphs = Pdf(self.export(doc, "require_searchable")).text_glyphs()
        self.assertEqual([source for source, _ in glyphs], ["fi", "é", "B"])
        self.assertGreater(glyphs[1][1][4], glyphs[0][1][4])

    def test_selected_artboards_resolve_their_own_fonts_in_delivery_order(self):
        self.install(font_bytes(cff=True))
        doc = self.document(text="A")
        operations = []
        for i, (board_id, source) in enumerate((("east", "fi"), ("west", "Bé"))):
            board = boards.BoardCliTests.board(self, board_id, 40, 40, x=i * 40)
            label = copy.deepcopy(doc["items"][0])
            label.update(id=f"{board_id}-label", parent=board_id)
            label["content"]["frame"]["text"] = source
            operations.extend(dict(op="add", item=item) for item in (board, label))
        doc = self.edit(doc, operations)
        result = self.invoke(
            dict(
                command="document.export",
                document=doc,
                font_root=str(self.store),
                format="pdf",
                pdf_options=dict(
                    text="require_searchable",
                    artboards=dict(type="ids", ids=["west", "east"]),
                ),
            )
        )
        pdf = Pdf(result)
        self.assertEqual([p["artboard_id"] for p in result["pages"]], ["west", "east"])
        self.assertEqual(
            ["".join(s for s, _ in pdf.text_glyphs(n)) for n in (0, 1)], ["Bé", "fi"]
        )
        self.assertEqual(result["pdf"]["text_delivery"]["embedded_font_programs"], 2)
        if pymupdf:
            with pymupdf.open(stream=pdf.data, filetype="pdf") as parsed:
                self.assertEqual(
                    [page.get_text().strip() for page in parsed], ["Bé", "fi"]
                )

    def test_path_text_preserves_rotated_and_scaled_glyph_axes(self):
        self.install(font_bytes())
        doc = self.document(
            text="AB",
            wrap=False,
            path=line((15, 30), (45, 8)),
            style=dict(
                font_id="geometry",
                size=12,
                horizontal_scale=1.5,
                vertical_scale=0.75,
                fill=[110, 70, 210, 255],
            ),
        )
        doc["resolution_ppi"] = 72
        layout = self.inspect(doc)["layout"]["glyphs"]
        glyphs = Pdf(self.export(doc, "require_searchable")).text_glyphs()
        self.assertEqual([source for source, _ in glyphs], ["A", "B"])
        for glyph, (_, matrix) in zip(layout, glyphs):
            a, b, c, d, _, _ = glyph["path"]["transform"]
            x, y = glyph["origin"]
            expected = [18 * a, -18 * b, -9 * c, 9 * d, x, doc["height"] - y]
            for actual, target in zip(matrix, expected):
                self.assertAlmostEqual(actual, target, places=5)

    def test_curved_combining_cluster_retains_each_tangent_and_copies_once(self):
        source = "A\u0301"
        for cff, alpha in ((False, 1.0), (True, 1.0), (False, 0.5), (True, 0.5)):
            with self.subTest(cff=cff, alpha=alpha):
                # An off-center attachment samples a different tangent on the curve.
                self.install(font_bytes(cff, mark_anchor=(600, 750)))
                doc = self.document(
                    text=source,
                    wrap=False,
                    path=curved(start_offset=14),
                    style=dict(
                        font_id="geometry",
                        size=16,
                        horizontal_scale=1.25,
                        vertical_scale=0.75,
                        fill={"rgba": [0.1254, 0.3951, 0.7788, alpha]},
                    ),
                )
                doc["resolution_ppi"] = 72
                glyphs = self.inspect(doc)["layout"]["glyphs"]
                self.assertEqual(len(glyphs), 2)
                self.assertNotAlmostEqual(
                    glyphs[0]["path"]["tangent"][0],
                    glyphs[1]["path"]["tangent"][0],
                    places=3,
                )
                pdf = Pdf(self.export(doc, "require_searchable"))
                self.assertTrue(
                    any(b"0.1254 0.3951 0.7788 rg" in s for s in pdf.streams.values())
                )
                [(text, outer)] = pdf.text_glyphs()
                self.assertEqual(text, source)
                cluster = next(
                    v
                    for v in pdf.objects.values()
                    if isinstance(v, dict) and v.get("Subtype") == "Type3"
                )
                proc = pdf.streams[cluster["CharProcs"]["Cluster"]].decode()
                matrices = re.findall(r"^([-0-9. ]+) Tm", proc, re.MULTILINE)
                self.assertEqual(len(matrices), 2)
                for g, row in zip(glyphs, matrices):
                    matrix = list(map(float, row.split()))
                    matrix[4:] = [v / 1000 for v in matrix[4:]]
                    actual = multiply(outer, matrix)
                    x, y = g["origin"]
                    tx, ty = g["path"]["tangent"]
                    style = doc["items"][0]["content"]["frame"]["style"]
                    w = style["size"] * style["horizontal_scale"]
                    h = style["size"] * style["vertical_scale"]
                    expected = [tx * w, -ty * w, ty * h, tx * h, x, doc["height"] - y]
                    for value, target in zip(actual, expected):
                        self.assertAlmostEqual(value, target, places=6)
                if shutil.which("pdftotext"):
                    self.assertEqual(extracted_text(pdf.data), source)
                if pymupdf:
                    outline = Pdf(self.export(doc))
                    with pymupdf.open(
                        stream=pdf.data, filetype="pdf"
                    ) as f, pymupdf.open(stream=outline.data, filetype="pdf") as ref:
                        self.assertEqual(f[0].get_text().rstrip("\r\n"), source)
                        actual = f[0].get_pixmap(dpi=288, alpha=True)
                        reference = ref[0].get_pixmap(dpi=288, alpha=True)
                        self.assert_cluster_raster(actual, reference, 0.005)

    @unittest.skipUnless(
        pymupdf, "MuPDF renders the embedded font and extracts source text"
    )
    def test_independent_font_rendering_and_extraction(self):
        for cff in (False, True):
            for whole in (False, True):
                with self.subTest(cff=cff, whole=whole):
                    self.install(font_bytes(cff, 0x108 if whole else 8))
                    source = "AB fi é"
                    doc = self.document(text=source, wrap=False)
                    doc["resolution_ppi"] = 72
                    actual = Pdf(self.export(doc, "require_searchable")).data
                    reference = Pdf(self.export(doc)).data
                    with pymupdf.open(stream=actual, filetype="pdf") as f, pymupdf.open(
                        stream=reference, filetype="pdf"
                    ) as r:
                        self.assertEqual(f[0].get_text().rstrip("\r\n"), source)
                        a = f[0].get_pixmap(dpi=288, alpha=True)
                        b = r[0].get_pixmap(dpi=288, alpha=True)
                        self.assertEqual(a.irect, b.irect)
                        actual_rgba, reference_rgba = a.samples, b.samples
                        actual_alpha, reference_alpha = (
                            actual_rgba[3::4],
                            reference_rgba[3::4],
                        )
                        self.assertIn(255, reference_alpha)
                        # Glyph and path scan conversion can round antialiased edges differently.
                        # Check five coverage contours, every opaque color and total coverage error.
                        for threshold in (1, 64, 128, 192, 255):
                            self.assertEqual(
                                bytes(x >= threshold for x in actual_alpha),
                                bytes(x >= threshold for x in reference_alpha),
                            )
                        for i, alpha in enumerate(reference_alpha):
                            if alpha == 255:
                                self.assertEqual(
                                    actual_rgba[4 * i : 4 * i + 4],
                                    reference_rgba[4 * i : 4 * i + 4],
                                )
                        error = sum(
                            abs(x - y) for x, y in zip(actual_alpha, reference_alpha)
                        )
                        self.assertLess(error / sum(reference_alpha), 0.005)

    @unittest.skipUnless(
        shutil.which("pdftotext"), "An independent pdftotext executable is required"
    )
    def test_pdftotext_extraction(self):
        source = "AB fi é"
        for cff in (False, True):
            for whole in (False, True):
                with self.subTest(cff=cff, whole=whole):
                    self.install(font_bytes(cff, 0x108 if whole else 8))
                    doc = self.document(text=source, wrap=False)
                    actual = Pdf(self.export(doc, "require_searchable")).data
                    self.assertEqual(extracted_text(actual), source)
