"""Original static fonts, text extraction, embedding restrictions and page placement."""
import copy
import shutil
import struct
import subprocess
import unittest

from pdf_reader import Pdf
from synthetic_font import pack, checksum
from synthetic_unicode_font import ADVANCES, rectangle, sfnt, unicode_font
from synthetic_variable_font import tables, variable_font
import test_text_cli as text_cli
import test_boards_cli as boards
from test_path_text_cli import line
from test_pdf_blends_cli import pymupdf
import test_story_cli as story_cli


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


def font_bytes(cff=False, permissions=8):
    data = tables(unicode_font())
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
        shutil.which("pdftotext"), "Poppler independently extracts source text"
    )
    def test_poppler_extraction(self):
        source = "AB fi é"
        for cff in (False, True):
            for whole in (False, True):
                with self.subTest(cff=cff, whole=whole):
                    self.install(font_bytes(cff, 0x108 if whole else 8))
                    doc = self.document(text=source, wrap=False)
                    actual = Pdf(self.export(doc, "require_searchable")).data
                    output = subprocess.check_output(
                        ["pdftotext", "-enc", "UTF-8", "-", "-"],
                        input=actual,
                        timeout=10,
                    )
                    self.assertEqual(output.decode().rstrip("\r\n\f"), source)
