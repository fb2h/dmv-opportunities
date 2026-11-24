"""Minimal .xlsx read/write using the Python standard library.

Chosen so the reviewer loopback tool has no extra runtime dependency beyond
the repository's existing zipcodes requirement (unused here). Handles shared
strings and inline strings so a file edited in Excel/LibreOffice still imports.
"""
from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree as ET

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix if prefix != "m" else "", uri)

MAIN = NS["m"]


def _col_row(cell_ref):
    col = ""
    row = ""
    for ch in cell_ref:
        if ch.isalpha():
            col += ch
        else:
            row += ch
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch.upper()) - 64)
    return n, int(row or 1)


def _col_letter(n):
    out = ""
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def write_xlsx(sheets, path=None):
    """sheets: list of (name, rows) where rows are lists of strings."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types(len(sheets)))
        zf.writestr("_rels/.rels", _rels_root())
        zf.writestr("xl/_rels/workbook.xml.rels", _workbook_rels(len(sheets)))
        zf.writestr("xl/workbook.xml", _workbook_xml(sheets))
        zf.writestr("xl/styles.xml", _styles_xml())
        shared, sheet_xmls = _sheets_and_strings(sheets)
        zf.writestr("xl/sharedStrings.xml", shared)
        for i, xml in enumerate(sheet_xmls, start=1):
            zf.writestr(f"xl/worksheets/sheet{i}.xml", xml)
    data = buf.getvalue()
    if path:
        with open(path, "wb") as fh:
            fh.write(data)
    return data


def read_xlsx(data):
    """Return {sheet_name: [ {header: value, ...}, ... ]} using the first row as headers."""
    if isinstance(data, str):
        with open(data, "rb") as fh:
            data = fh.read()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = {info.filename for info in zf.infolist()}
        strings = _read_shared_strings(zf.read("xl/sharedStrings.xml")) if "xl/sharedStrings.xml" in names else []
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = _read_rels(zf.read("xl/_rels/workbook.xml.rels"))
        out = {}
        for sheet in wb.findall(f"{{{MAIN}}}sheets/{{{MAIN}}}sheet"):
            name = sheet.attrib.get("name", "Sheet")
            rid = sheet.attrib.get("{%s}id" % NS["r"])
            target = rels.get(rid)
            if not target:
                continue
            if target.startswith("/"):
                target = target.lstrip("/")
            elif not target.startswith("xl/"):
                target = "xl/" + target.lstrip("/")
            rows = _read_sheet(zf.read(target), strings)
            if not rows:
                out[name] = []
                continue
            headers = rows[0]
            records = []
            for row in rows[1:]:
                rec = {}
                for i, header in enumerate(headers):
                    if not header:
                        continue
                    rec[header] = row[i] if i < len(row) else ""
                if any(str(v).strip() for v in rec.values()):
                    records.append(rec)
            out[name] = records
        return out


def _read_rels(xml):
    root = ET.fromstring(xml)
    out = {}
    for rel in root:
        out[rel.attrib.get("Id")] = rel.attrib.get("Target")
    return out


def _read_shared_strings(xml):
    root = ET.fromstring(xml)
    out = []
    for si in root.findall(f"{{{MAIN}}}si"):
        texts = [t.text or "" for t in si.iter(f"{{{MAIN}}}t")]
        out.append("".join(texts))
    return out


def _cell_text(cell, strings):
    t = cell.attrib.get("t")
    is_el = cell.find(f"{{{MAIN}}}is")
    v = cell.find(f"{{{MAIN}}}v")
    if t == "inlineStr" and is_el is not None:
        return "".join(n.text or "" for n in is_el.iter(f"{{{MAIN}}}t"))
    if v is None or v.text is None:
        return ""
    if t == "s":
        try:
            return strings[int(v.text)]
        except (IndexError, ValueError):
            return v.text
    return v.text


def _read_sheet(xml, strings):
    root = ET.fromstring(xml)
    grid = {}
    max_col, max_row = 0, 0
    for row in root.findall(f"{{{MAIN}}}sheetData/{{{MAIN}}}row"):
        for cell in row.findall(f"{{{MAIN}}}c"):
            ref = cell.attrib.get("r")
            if not ref:
                continue
            col, ridx = _col_row(ref)
            grid[(col, ridx)] = _cell_text(cell, strings)
            max_col = max(max_col, col)
            max_row = max(max_row, ridx)
    rows = []
    for ridx in range(1, max_row + 1):
        rows.append([grid.get((c, ridx), "") for c in range(1, max_col + 1)])
    return rows


def _sheets_and_strings(sheets):
    unique = []
    index = {}
    def intern(text):
        text = "" if text is None else str(text)
        if text not in index:
            index[text] = len(unique)
            unique.append(text)
        return index[text]

    sheet_xmls = []
    for _, rows in sheets:
        sd = ET.Element("sheetData")
        for ridx, row in enumerate(rows, start=1):
            row_el = ET.SubElement(sd, "row", r=str(ridx))
            for cidx, value in enumerate(row, start=1):
                ref = f"{_col_letter(cidx)}{ridx}"
                cell = ET.SubElement(row_el, "c", r=ref, t="s")
                if ridx == 1:
                    cell.set("s", "1")
                ET.SubElement(cell, "v").text = str(intern(value))
        ws = ET.Element("worksheet", xmlns=MAIN)
        ET.SubElement(ws, "sheetViews")
        view = ET.SubElement(ws.find("sheetViews"), "sheetView", workbookViewId="0")
        ET.SubElement(view, "pane", ySplit="1", topLeftCell="A2", activePane="bottomLeft", state="frozen")
        ET.SubElement(ws, "sheetFormatPr", defaultRowHeight="15")
        cols = ET.SubElement(ws, "cols")
        ET.SubElement(cols, "col", min="1", max="20", width="36", customWidth="1")
        ws.append(sd)
        sheet_xmls.append(ET.tostring(ws, encoding="unicode", xml_declaration=False))

    sst = ET.Element("sst", xmlns=MAIN, count=str(len(unique)), uniqueCount=str(len(unique)))
    for text in unique:
        si = ET.SubElement(sst, "si")
        t = ET.SubElement(si, "t")
        if text[:1].isspace() or text[-1:].isspace():
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = text
    shared = ET.tostring(sst, encoding="unicode", xml_declaration=False)
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + shared, [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + x for x in sheet_xmls
    ]


def _content_types(n):
    overrides = "\n".join(
        f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(1, n + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="{NS["ct"]}">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
{overrides}
</Types>
'''


def _rels_root():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{NS["pr"]}">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
'''


def _workbook_rels(n):
    rels = "\n".join(
        f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
        for i in range(1, n + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{NS["pr"]}">
{rels}
<Relationship Id="rId{n + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
<Relationship Id="rId{n + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
'''


def _workbook_xml(sheets):
    sheets_xml = "\n".join(
        f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>'
        for i, (name, _) in enumerate(sheets, start=1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="{MAIN}" xmlns:r="{NS["r"]}">
<sheets>
{sheets_xml}
</sheets>
</workbook>
'''


def _styles_xml():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="{MAIN}">
<fonts count="2">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><name val="Calibri"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFF2CC"/></patternFill></fill>
</fills>
<borders count="1"><border/></borders>
<cellXfs count="2">
<xf fontId="0" fillId="0" borderId="0"/>
<xf fontId="1" fillId="2" borderId="0" applyFont="1" applyFill="1"/>
</cellXfs>
</styleSheet>
'''
