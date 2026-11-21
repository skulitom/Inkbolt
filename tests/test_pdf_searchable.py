"""Original static fonts, text extraction, embedding restrictions and page placement."""
import copy
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
import unittest

from pdf_reader import Pdf, multiply
from synthetic_font import pack, checksum
from synthetic_unicode_font import ADVANCES, rectangle, sfnt, unicode_font
from synthetic_variable_font import tables, variable_font
import test_text_cli as text_cli
import test_boards_cli as boards
from test_path_text_cli import curved, line
from test_pdf_blends_cli import pymupdf
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
        self.install(font_bytes())
        for fill in ([10, 80, 150, 128], {"rgba": [0.12, 0.38, 0.78, 0.9999]}):
            with self.subTest(fill=fill):
                doc = self.document(
                    text="A\u0301",
                    wrap=False,
                    style=dict(font_id="geometry", size=12, fill=fill),
                )
                result = self.export(doc, "searchable")
                self.assertEqual(
                    result["pdf"]["text_delivery"]["outlined_items_by_reason"],
                    {"cluster_paint": 1},
                )
                self.assertEqual(Pdf(result).data, Pdf(self.export(doc)).data)
                self.assertIn(
                    "cluster_paint",
                    self.export(doc, "require_searchable", 1)["message"],
                )

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
        for cff in (False, True):
            with self.subTest(cff=cff):
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
                        fill={"rgba": [0.1254, 0.3951, 0.7788, 1.0]},
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
