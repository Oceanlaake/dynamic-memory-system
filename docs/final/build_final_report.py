"""Build the editable DOCX source for the five-page final report.

Pandoc handles Markdown, tables, and image embedding.  This wrapper inserts
explicit Word page breaks and normalizes the generated document styles so the
five framework sections remain one A4 page each.
"""

from __future__ import annotations

import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "final-report.md"
OUTPUT = HERE / "final-report.docx"

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ET.register_namespace("w", W)


def _page_break_source() -> str:
    text = SOURCE.read_text(encoding="utf-8")
    page_break = (
        "\n```{=openxml}\n"
        '<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n'
        "```\n"
    )
    return text.replace("\n---\n", page_break)


def _set_font(style: ET.Element, western: str, east_asia: str, half_points: int) -> None:
    rpr = style.find(f"{{{W}}}rPr")
    if rpr is None:
        rpr = ET.SubElement(style, f"{{{W}}}rPr")
    fonts = rpr.find(f"{{{W}}}rFonts")
    if fonts is None:
        fonts = ET.SubElement(rpr, f"{{{W}}}rFonts")
    for key in ("ascii", "hAnsi", "cs"):
        fonts.set(f"{{{W}}}{key}", western)
    fonts.set(f"{{{W}}}eastAsia", east_asia)
    size = rpr.find(f"{{{W}}}sz")
    if size is None:
        size = ET.SubElement(rpr, f"{{{W}}}sz")
    size.set(f"{{{W}}}val", str(half_points))
    size_cs = rpr.find(f"{{{W}}}szCs")
    if size_cs is None:
        size_cs = ET.SubElement(rpr, f"{{{W}}}szCs")
    size_cs.set(f"{{{W}}}val", str(half_points))


def _set_paragraph_spacing(style: ET.Element, before: int, after: int, line: int) -> None:
    ppr = style.find(f"{{{W}}}pPr")
    if ppr is None:
        ppr = ET.SubElement(style, f"{{{W}}}pPr")
    spacing = ppr.find(f"{{{W}}}spacing")
    if spacing is None:
        spacing = ET.SubElement(ppr, f"{{{W}}}spacing")
    spacing.set(f"{{{W}}}before", str(before))
    spacing.set(f"{{{W}}}after", str(after))
    spacing.set(f"{{{W}}}line", str(line))
    spacing.set(f"{{{W}}}lineRule", "auto")


def _patch_docx(path: Path) -> None:
    with tempfile.TemporaryDirectory() as temp_name:
        temp = Path(temp_name)
        with zipfile.ZipFile(path) as archive:
            archive.extractall(temp)

        styles_path = temp / "word" / "styles.xml"
        styles = ET.parse(styles_path)
        root = styles.getroot()
        by_id = {
            style.get(f"{{{W}}}styleId"): style
            for style in root.findall(f"{{{W}}}style")
        }
        normal = by_id.get("Normal")
        if normal is not None:
            _set_font(normal, "Arial", "Heiti SC", 21)
            _set_paragraph_spacing(normal, 0, 48, 240)
        table = by_id.get("Table")
        if table is None:
            table = by_id.get("TableNormal")
        if table is not None:
            _set_font(table, "Arial", "Heiti SC", 18)
            _set_paragraph_spacing(table, 0, 12, 220)
        heading_sizes = {"Title": 36, "Heading1": 30, "Heading2": 26, "Heading3": 22}
        for style_id, size in heading_sizes.items():
            style = by_id.get(style_id)
            if style is not None:
                _set_font(style, "Arial", "Heiti SC", size)
                _set_paragraph_spacing(style, 90, 45, 220)
        styles.write(styles_path, encoding="UTF-8", xml_declaration=True)

        document_path = temp / "word" / "document.xml"
        document = ET.parse(document_path)
        doc_root = document.getroot()
        for section in doc_root.findall(f".//{{{W}}}sectPr"):
            page_size = section.find(f"{{{W}}}pgSz")
            if page_size is None:
                page_size = ET.SubElement(section, f"{{{W}}}pgSz")
            page_size.set(f"{{{W}}}w", "11906")
            page_size.set(f"{{{W}}}h", "16838")
            margin = section.find(f"{{{W}}}pgMar")
            if margin is None:
                margin = ET.SubElement(section, f"{{{W}}}pgMar")
            for key, value in {
                "top": "720", "bottom": "650", "left": "850", "right": "850",
                "header": "360", "footer": "360", "gutter": "0",
            }.items():
                margin.set(f"{{{W}}}{key}", value)
        document.write(document_path, encoding="UTF-8", xml_declaration=True)

        rebuilt = path.with_suffix(".rebuilt.docx")
        with zipfile.ZipFile(rebuilt, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in sorted(temp.rglob("*")):
                if item.is_file():
                    archive.write(item, item.relative_to(temp))
        rebuilt.replace(path)


def main() -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", encoding="utf-8", delete=False, dir=HERE,
    ) as temp:
        temp.write(_page_break_source())
        temp_source = Path(temp.name)
    try:
        subprocess.run(
            [
                "pandoc", str(temp_source), "--from=markdown+raw_attribute",
                "--to=docx", f"--resource-path={HERE}", "--standalone",
                f"--output={OUTPUT}",
            ],
            check=True,
            cwd=HERE,
        )
        _patch_docx(OUTPUT)
    finally:
        temp_source.unlink(missing_ok=True)
    print(OUTPUT)


if __name__ == "__main__":
    main()
