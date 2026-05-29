"""Generate presentation and GitHub-viewable demo assets for Smart Todo.

This script intentionally uses only Python's standard library. It creates:
  - demo/Smart-Todo-Code-and-Dashboard-Demo.pptx
  - demo/smart-todo-demo-flow.gif
  - demo/DEMO.md
  - demo/demo-script.md
  - demo/screenshots/*.png

The GIF and PNG screenshots are generated without ffmpeg, Playwright, or PIL.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import html
import math
import struct
import zipfile
import zlib


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "demo"
PPTX_PATH = DEMO_DIR / "Smart-Todo-Code-and-Dashboard-Demo.pptx"
GIF_PATH = DEMO_DIR / "smart-todo-demo-flow.gif"
DEMO_MD_PATH = DEMO_DIR / "DEMO.md"
SCRIPT_PATH = DEMO_DIR / "demo-script.md"
SCREENSHOTS_DIR = DEMO_DIR / "screenshots"

EMU_PER_INCH = 914400
SLIDE_W = int(13.333 * EMU_PER_INCH)
SLIDE_H = int(7.5 * EMU_PER_INCH)


@dataclass(frozen=True)
class Slide:
    title: str
    subtitle: str
    bullets: tuple[str, ...]
    footer: str = "Smart Todo API demo"


SLIDES = (
    Slide(
        "Smart Todo Priority Predictor",
        "A compact ML API with a dashboard, load-test hooks, and self-healing tests.",
        (
            "Goal: classify tasks as High, Medium, or Low priority.",
            "Main flow: data/tasks.csv -> train.py -> model.joblib -> app.py -> dashboard.",
            "Demo URL: http://127.0.0.1:5000/",
        ),
    ),
    Slide(
        "Project Structure",
        "The repo is organized around one small end-to-end ML service.",
        (
            "data/tasks.csv: 200 labeled task examples.",
            "train.py: trains TF-IDF + Logistic Regression.",
            "app.py: Flask API, dashboard routes, k6 and pytest runners.",
            "templates/dashboard.html: browser UI for predictions, load tests, and tests.",
            "tests/: API contract tests plus the field-alias resolver.",
        ),
    ),
    Slide(
        "Dataset And Training",
        "Training turns short task text into a priority classifier.",
        (
            "Each CSV row has task text and a priority label.",
            "TfidfVectorizer converts text into numeric features.",
            "LogisticRegression learns which phrases point to High, Medium, or Low.",
            "The final trained pipeline is saved to model.joblib.",
        ),
    ),
    Slide(
        "Flask API",
        "app.py loads the model once and exposes a small prediction API.",
        (
            "GET /health returns status ok.",
            "POST /predict expects JSON: {\"task\":\"Fix production bug\"}.",
            "The model returns class probabilities; app.py selects the highest one.",
            "Response shape: {\"priority\":\"High\", \"confidence\":0.9166}.",
        ),
    ),
    Slide(
        "Dashboard Walkthrough",
        "The first screen is the usable demo, not a landing page.",
        (
            "Phase 1: type a task and click Predict.",
            "Phase 2: configure request method, body, stages, VUs, and thresholds.",
            "Phase 3: run tests against the original API or a mutated API.",
            "The dashboard streams command output back into the browser.",
        ),
    ),
    Slide(
        "Self-Healing Tests",
        "The tests tolerate small response-field renames while still warning you.",
        (
            "Canonical fields: priority and confidence.",
            "Known aliases: priority -> level, urgency, rank, severity, importance.",
            "Known aliases: confidence -> score, probability, certainty, prob.",
            "If an alias is used, tests pass with a visible WARNING.",
        ),
    ),
    Slide(
        "Load-Test Support",
        "The dashboard can drive k6 scripts once k6 is installed.",
        (
            "k6/load.js receives its settings from environment variables.",
            "reports/analysis.md summarizes ramp-up and spike results.",
            "Previous result: ramp-up passed; spike revealed Flask dev-server limits.",
            "This identifies the server as the bottleneck, not the ML model.",
        ),
    ),
    Slide(
        "Live Demo Script",
        "Recommended order for presenting the project.",
        (
            "1. Open data/tasks.csv and show example labels.",
            "2. Open train.py and explain TF-IDF + Logistic Regression.",
            "3. Open app.py and explain /predict.",
            "4. Open dashboard, run three sample predictions.",
            "5. Run original and mutated self-healing tests.",
        ),
    ),
    Slide(
        "Close",
        "A complete mini lifecycle for a simple AI-backed API.",
        (
            "Training, serving, dashboard UX, performance hooks, and API contract tests.",
            "Easy to run locally: .venv/bin/python app.py.",
            "Useful next step: install k6 and run the dashboard load-test builder live.",
        ),
    ),
)


def esc(value: str) -> str:
    return html.escape(value, quote=False)


def shape_rect(x: int, y: int, w: int, h: int, fill: str, line: str | None = None) -> str:
    line_xml = "<a:ln><a:noFill/></a:ln>" if line is None else (
        f"<a:ln w=\"12700\"><a:solidFill><a:srgbClr val=\"{line}\"/></a:solidFill></a:ln>"
    )
    return f"""
      <p:sp>
        <p:nvSpPr><p:cNvPr id="1" name="Background"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>
          {line_xml}
        </p:spPr>
      </p:sp>
    """


def text_shape(
    shape_id: int,
    x: int,
    y: int,
    w: int,
    h: int,
    lines: list[str],
    size: int,
    color: str,
    bold: bool = False,
) -> str:
    paragraphs = []
    for line in lines:
        paragraphs.append(
            f"""
            <a:p>
              <a:r>
                <a:rPr lang="en-US" sz="{size}" b="{1 if bold else 0}">
                  <a:solidFill><a:srgbClr val="{color}"/></a:solidFill>
                </a:rPr>
                <a:t>{esc(line)}</a:t>
              </a:r>
            </a:p>
            """
        )
    return f"""
      <p:sp>
        <p:nvSpPr><p:cNvPr id="{shape_id}" name="Text {shape_id}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:noFill/>
          <a:ln><a:noFill/></a:ln>
        </p:spPr>
        <p:txBody>
          <a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0"/>
          <a:lstStyle/>
          {''.join(paragraphs)}
        </p:txBody>
      </p:sp>
    """


def slide_xml(slide: Slide, index: int) -> str:
    margin = int(0.55 * EMU_PER_INCH)
    top_bar_h = int(0.86 * EMU_PER_INCH)
    title_h = int(0.65 * EMU_PER_INCH)
    content_x = margin
    content_y = int(1.55 * EMU_PER_INCH)
    content_w = SLIDE_W - 2 * margin
    bullet_lines = [f"- {bullet}" for bullet in slide.bullets]
    accent = "2563EB"
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
      {shape_rect(0, 0, SLIDE_W, SLIDE_H, "F8FAFC")}
      {shape_rect(0, 0, SLIDE_W, top_bar_h, "0F172A")}
      {shape_rect(margin, int(1.18 * EMU_PER_INCH), int(1.45 * EMU_PER_INCH), int(0.08 * EMU_PER_INCH), accent)}
      {text_shape(2, margin, int(0.19 * EMU_PER_INCH), SLIDE_W - 2 * margin, title_h, [slide.title], 3400, "FFFFFF", True)}
      {text_shape(3, margin, int(0.96 * EMU_PER_INCH), SLIDE_W - 2 * margin, int(0.42 * EMU_PER_INCH), [slide.subtitle], 1900, "334155", False)}
      {shape_rect(content_x, content_y, content_w, int(4.8 * EMU_PER_INCH), "FFFFFF", "CBD5E1")}
      {text_shape(4, content_x + int(0.45 * EMU_PER_INCH), content_y + int(0.45 * EMU_PER_INCH), content_w - int(0.9 * EMU_PER_INCH), int(3.8 * EMU_PER_INCH), bullet_lines, 2050, "0F172A", False)}
      {text_shape(5, margin, SLIDE_H - int(0.42 * EMU_PER_INCH), int(7 * EMU_PER_INCH), int(0.25 * EMU_PER_INCH), [slide.footer], 950, "64748B", False)}
      {text_shape(6, SLIDE_W - int(1.35 * EMU_PER_INCH), SLIDE_H - int(0.42 * EMU_PER_INCH), int(0.8 * EMU_PER_INCH), int(0.25 * EMU_PER_INCH), [str(index)], 950, "64748B", False)}
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>
"""


def write_pptx() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    slide_overrides = "\n".join(
        f'<Override PartName="/ppt/slides/slide{i}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        for i in range(1, len(SLIDES) + 1)
    )
    content_types = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
  {slide_overrides}
</Types>
"""
    sld_ids = "\n".join(
        f'<p:sldId id="{255 + i}" r:id="rId{i + 1}"/>' for i in range(1, len(SLIDES) + 1)
    )
    pres_rels = "\n".join(
        [
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>',
            *[
                f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>'
                for i in range(1, len(SLIDES) + 1)
            ],
        ]
    )
    presentation = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
                xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>
  <p:sldIdLst>{sld_ids}</p:sldIdLst>
  <p:sldSz cx="{SLIDE_W}" cy="{SLIDE_H}" type="wide"/>
  <p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>
"""
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""
    pres_rels_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  {pres_rels}
</Relationships>
"""
    slide_master = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
             xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
  <p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles>
</p:sldMaster>
"""
    slide_master_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>
"""
    slide_layout = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
             xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
             type="blank" preserve="1">
  <p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>
"""
    slide_layout_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>
"""
    theme = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="SmartTodo">
  <a:themeElements>
    <a:clrScheme name="SmartTodo">
      <a:dk1><a:srgbClr val="0F172A"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="334155"/></a:dk2><a:lt2><a:srgbClr val="F8FAFC"/></a:lt2>
      <a:accent1><a:srgbClr val="2563EB"/></a:accent1><a:accent2><a:srgbClr val="16A34A"/></a:accent2>
      <a:accent3><a:srgbClr val="F59E0B"/></a:accent3><a:accent4><a:srgbClr val="DC2626"/></a:accent4>
      <a:accent5><a:srgbClr val="7C3AED"/></a:accent5><a:accent6><a:srgbClr val="0891B2"/></a:accent6>
      <a:hlink><a:srgbClr val="2563EB"/></a:hlink><a:folHlink><a:srgbClr val="7C3AED"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="Office"><a:majorFont><a:latin typeface="Aptos Display"/></a:majorFont><a:minorFont><a:latin typeface="Aptos"/></a:minorFont></a:fontScheme>
    <a:fmtScheme name="Office"><a:fillStyleLst/><a:lnStyleLst/><a:effectStyleLst/><a:bgFillStyleLst/></a:fmtScheme>
  </a:themeElements>
</a:theme>
"""
    core = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/"
                   xmlns:dcterms="http://purl.org/dc/terms/"
                   xmlns:dcmitype="http://purl.org/dc/dcmitype/"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Smart Todo Code And Dashboard Demo</dc:title>
  <dc:creator>Codex</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>
"""
    app = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
            xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Codex</Application>
  <PresentationFormat>On-screen Show (16:9)</PresentationFormat>
  <Slides>{len(SLIDES)}</Slides>
  <Company>LabsKraf</Company>
</Properties>
"""
    slide_rel = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>
"""
    with zipfile.ZipFile(PPTX_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("docProps/core.xml", core)
        zf.writestr("docProps/app.xml", app)
        zf.writestr("ppt/presentation.xml", presentation)
        zf.writestr("ppt/_rels/presentation.xml.rels", pres_rels_xml)
        zf.writestr("ppt/slideMasters/slideMaster1.xml", slide_master)
        zf.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", slide_master_rels)
        zf.writestr("ppt/slideLayouts/slideLayout1.xml", slide_layout)
        zf.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", slide_layout_rels)
        zf.writestr("ppt/theme/theme1.xml", theme)
        for i, slide in enumerate(SLIDES, start=1):
            zf.writestr(f"ppt/slides/slide{i}.xml", slide_xml(slide, i))
            zf.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", slide_rel)


FONT = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["00111", "00010", "00010", "00010", "10010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    " ": ["000", "000", "000", "000", "000", "000", "000"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    ".": ["000", "000", "000", "000", "000", "011", "011"],
    ",": ["000", "000", "000", "000", "000", "010", "100"],
    ":": ["000", "010", "010", "000", "010", "010", "000"],
    "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
    "(": ["0010", "0100", "1000", "1000", "1000", "0100", "0010"],
    ")": ["1000", "0100", "0010", "0010", "0010", "0100", "1000"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    "%": ["11001", "11010", "00010", "00100", "01000", "01011", "10011"],
    ">": ["1000", "0100", "0010", "0001", "0010", "0100", "1000"],
    "<": ["0001", "0010", "0100", "1000", "0100", "0010", "0001"],
    "=": ["00000", "11111", "00000", "00000", "11111", "00000", "00000"],
    "{": ["0011", "0100", "0100", "1000", "0100", "0100", "0011"],
    "}": ["1100", "0010", "0010", "0001", "0010", "0010", "1100"],
    "\"": ["101", "101", "000", "000", "000", "000", "000"],
}


Color = tuple[int, int, int]


def rgb(hex_color: str) -> Color:
    hex_color = hex_color.strip("#")
    return int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)


def new_frame(w: int, h: int, color: Color) -> bytearray:
    return bytearray(color * (w * h))


def fill_rect(frame: bytearray, w: int, h: int, x: int, y: int, rw: int, rh: int, color: Color) -> None:
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(w, x + rw), min(h, y + rh)
    r, g, b = color
    for yy in range(y0, y1):
        row = yy * w * 3
        for xx in range(x0, x1):
            i = row + xx * 3
            frame[i : i + 3] = bytes((r, g, b))


def rect_outline(frame: bytearray, w: int, h: int, x: int, y: int, rw: int, rh: int, color: Color, thickness: int = 2) -> None:
    fill_rect(frame, w, h, x, y, rw, thickness, color)
    fill_rect(frame, w, h, x, y + rh - thickness, rw, thickness, color)
    fill_rect(frame, w, h, x, y, thickness, rh, color)
    fill_rect(frame, w, h, x + rw - thickness, y, thickness, rh, color)


def draw_char(frame: bytearray, w: int, h: int, x: int, y: int, ch: str, color: Color, scale: int) -> int:
    pattern = FONT.get(ch.upper(), FONT[" "])
    for row, bits in enumerate(pattern):
        for col, bit in enumerate(bits):
            if bit == "1":
                fill_rect(frame, w, h, x + col * scale, y + row * scale, scale, scale, color)
    return (len(pattern[0]) + 1) * scale


def draw_text(frame: bytearray, w: int, h: int, x: int, y: int, text: str, color: Color, scale: int = 2) -> None:
    xx = x
    for ch in text:
        xx += draw_char(frame, w, h, xx, y, ch, color, scale)


def text_width(text: str, scale: int) -> int:
    return sum((len(FONT.get(ch.upper(), FONT[" "])[0]) + 1) * scale for ch in text)


def draw_wrapped(frame: bytearray, w: int, h: int, x: int, y: int, text: str, color: Color, max_width: int, scale: int = 2, line_gap: int = 5) -> None:
    words = text.split()
    line = ""
    yy = y
    line_height = 7 * scale + line_gap
    for word in words:
        test = word if not line else f"{line} {word}"
        if text_width(test, scale) <= max_width:
            line = test
        else:
            draw_text(frame, w, h, x, yy, line, color, scale)
            yy += line_height
            line = word
    if line:
        draw_text(frame, w, h, x, yy, line, color, scale)


def box(frame: bytearray, w: int, h: int, x: int, y: int, rw: int, rh: int, title: str, lines: list[str], fill: str = "FFFFFF", edge: str = "CBD5E1") -> None:
    fill_rect(frame, w, h, x, y, rw, rh, rgb(fill))
    rect_outline(frame, w, h, x, y, rw, rh, rgb(edge), 2)
    draw_text(frame, w, h, x + 12, y + 12, title, rgb("0F172A"), 2)
    yy = y + 42
    for line in lines:
        draw_wrapped(frame, w, h, x + 12, yy, line, rgb("334155"), rw - 24, 2)
        yy += 34


def add_header(frame: bytearray, w: int, h: int, title: str, step: str) -> None:
    fill_rect(frame, w, h, 0, 0, w, 52, rgb("0F172A"))
    draw_text(frame, w, h, 18, 16, title, rgb("FFFFFF"), 2)
    draw_text(frame, w, h, w - text_width(step, 2) - 18, 18, step, rgb("93C5FD"), 2)


def scene_frame(scene: int, tick: int, scene_ticks: int, w: int, h: int) -> bytearray:
    frame = new_frame(w, h, rgb("F8FAFC"))
    titles = [
        "SMART TODO PRIORITY PREDICTOR",
        "1. DATASET",
        "2. TRAINING PIPELINE",
        "3. FLASK API",
        "4. DASHBOARD PREDICTION",
        "5. LOAD TEST BUILDER",
        "6. SELF-HEALING TESTS",
        "READY FOR GITHUB DEMO",
    ]
    add_header(frame, w, h, titles[scene], f"{scene + 1}/8")
    if scene == 0:
        draw_text(frame, w, h, 44, 92, "DATA -> MODEL -> API -> DASHBOARD", rgb("2563EB"), 3)
        box(frame, w, h, 56, 154, 170, 82, "INPUT", ["Task text from CSV"])
        box(frame, w, h, 250, 154, 170, 82, "MODEL", ["TF-IDF + Logistic Regression"])
        box(frame, w, h, 444, 154, 140, 82, "OUTPUT", ["High / Medium / Low"])
    elif scene == 1:
        box(frame, w, h, 34, 78, 572, 226, "data/tasks.csv", [
            "Fix production outage in payments service -> High",
            "Prepare quarterly business review deck -> Medium",
            "Read newsletter from cloud provider -> Low",
            "200 labeled examples train the classifier.",
        ])
    elif scene == 2:
        box(frame, w, h, 34, 92, 162, 90, "STEP 1", ["Clean task text"])
        box(frame, w, h, 238, 92, 162, 90, "STEP 2", ["TF-IDF features"])
        box(frame, w, h, 442, 92, 162, 90, "STEP 3", ["Logistic regression"])
        box(frame, w, h, 150, 222, 340, 70, "OUTPUT", ["Saved as model.joblib"])
    elif scene == 3:
        box(frame, w, h, 34, 80, 270, 210, "POST /predict", [
            "{\"task\":\"Fix production bug\"}",
            "Validate request body",
            "Call model.predict_proba",
        ])
        box(frame, w, h, 336, 80, 270, 210, "JSON RESPONSE", [
            "{\"priority\":\"High\",",
            " \"confidence\":0.9166}",
            "Highest probability wins",
        ])
    elif scene == 4:
        box(frame, w, h, 34, 78, 572, 226, "Dashboard Phase 1", [])
        fill_rect(frame, w, h, 62, 136, 392, 38, rgb("FFFFFF"))
        rect_outline(frame, w, h, 62, 136, 392, 38, rgb("CBD5E1"))
        task = "Resolve P0 incident on checkout API"
        shown = task[: max(1, math.ceil(len(task) * min(1, tick / max(1, scene_ticks // 2))))]
        draw_text(frame, w, h, 72, 148, shown, rgb("0F172A"), 2)
        fill_rect(frame, w, h, 468, 136, 92, 38, rgb("2563EB"))
        draw_text(frame, w, h, 482, 148, "PREDICT", rgb("FFFFFF"), 2)
        if tick > scene_ticks // 2:
            fill_rect(frame, w, h, 62, 204, 498, 62, rgb("EFF6FF"))
            rect_outline(frame, w, h, 62, 204, 498, 62, rgb("93C5FD"))
            draw_text(frame, w, h, 76, 222, "RESULT: HIGH PRIORITY", rgb("991B1B"), 2)
            draw_text(frame, w, h, 76, 246, "CONFIDENCE: 91.66%", rgb("334155"), 2)
    elif scene == 5:
        box(frame, w, h, 34, 74, 270, 220, "Request", [
            "URL: any API endpoint",
            "Method: GET or POST",
            "Optional headers",
            "Paste private curls locally",
        ])
        box(frame, w, h, 336, 74, 270, 220, "Load Shape", [
            "Ramp-up: 1 -> 10 -> 50 VUs",
            "Spike: 5 -> 100 -> 5 VUs",
            "Requires k6 installed locally",
            "Reports saved under reports/",
        ])
    elif scene == 6:
        box(frame, w, h, 34, 76, 270, 218, "Original API", [
            "priority + confidence",
            "Tests read canonical fields",
            "Expected result: 7 passed",
        ])
        box(frame, w, h, 336, 76, 270, 218, "Mutated API", [
            "level + score",
            "Resolver maps aliases",
            "Tests pass with warnings",
        ])
    else:
        draw_text(frame, w, h, 48, 94, "DEMO MATERIALS ADDED", rgb("16A34A"), 3)
        box(frame, w, h, 56, 160, 528, 120, "Files", [
            "demo/Smart-Todo-Code-and-Dashboard-Demo.pptx",
            "demo/smart-todo-demo-flow.gif",
            "demo/DEMO.md",
            "demo/demo-script.md",
        ])
    fill_rect(frame, w, h, 0, h - 26, w, 26, rgb("E2E8F0"))
    draw_text(frame, w, h, 18, h - 18, "Open dashboard: http://127.0.0.1:5000/", rgb("475569"), 1)
    return frame


def avi_chunk(tag: bytes, data: bytes) -> bytes:
    pad = b"\x00" if len(data) % 2 else b""
    return tag + struct.pack("<I", len(data)) + data + pad


def avi_list(tag: bytes, data: bytes) -> bytes:
    payload = tag + data
    pad = b"\x00" if len(payload) % 2 else b""
    return b"LIST" + struct.pack("<I", len(payload)) + payload + pad


def frame_to_dib(frame: bytearray, w: int, h: int) -> bytes:
    rows = []
    for y in range(h - 1, -1, -1):
        row = frame[y * w * 3 : (y + 1) * w * 3]
        bgr = bytearray(len(row))
        for i in range(0, len(row), 3):
            bgr[i] = row[i + 2]
            bgr[i + 1] = row[i + 1]
            bgr[i + 2] = row[i]
        rows.append(bytes(bgr))
    return b"".join(rows)


def write_avi(frames: list[bytearray], path: Path, w: int, h: int, fps: int) -> None:
    frame_size = w * h * 3
    n = len(frames)
    main_header = struct.pack(
        "<IIIIIIIIII4I",
        int(1_000_000 / fps),
        frame_size * fps,
        0,
        0x10,
        n,
        0,
        1,
        frame_size,
        w,
        h,
        0,
        0,
        0,
        0,
    )
    stream_header = struct.pack(
        "<4s4sIHHIIIIIIIIhhhh",
        b"vids",
        b"DIB ",
        0,
        0,
        0,
        0,
        1,
        fps,
        0,
        n,
        frame_size,
        0xFFFFFFFF,
        0,
        0,
        0,
        w,
        h,
    )
    bitmap_info = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, frame_size, 0, 0, 0, 0)
    hdrl = avi_list(
        b"hdrl",
        avi_chunk(b"avih", main_header)
        + avi_list(b"strl", avi_chunk(b"strh", stream_header) + avi_chunk(b"strf", bitmap_info)),
    )
    movi_payload = bytearray()
    idx_entries = []
    for frame in frames:
        data = frame_to_dib(frame, w, h)
        offset = 4 + len(movi_payload)
        chunk = avi_chunk(b"00db", data)
        movi_payload.extend(chunk)
        idx_entries.append(struct.pack("<4sIII", b"00db", 0x10, offset, len(data)))
    movi = avi_list(b"movi", bytes(movi_payload))
    idx1 = avi_chunk(b"idx1", b"".join(idx_entries))
    body = hdrl + movi + idx1
    path.write_bytes(b"RIFF" + struct.pack("<I", 4 + len(body)) + b"AVI " + body)


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def write_png(frame: bytearray, path: Path, w: int, h: int) -> None:
    rows = bytearray()
    for y in range(h):
        rows.append(0)  # PNG filter type 0: no filtering.
        rows.extend(frame[y * w * 3 : (y + 1) * w * 3])
    data = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(bytes(rows), level=9))
        + png_chunk(b"IEND", b"")
    )
    path.write_bytes(data)


def palette_for_frames(frames: list[bytearray]) -> tuple[list[Color], dict[Color, int]]:
    palette: list[Color] = []
    index: dict[Color, int] = {}
    for frame in frames:
        for i in range(0, len(frame), 3):
            color = (frame[i], frame[i + 1], frame[i + 2])
            if color not in index:
                if len(palette) >= 256:
                    raise ValueError("GIF palette exceeded 256 colors")
                index[color] = len(palette)
                palette.append(color)
    return palette, index


def frame_to_indices(frame: bytearray, palette_index: dict[Color, int]) -> bytes:
    out = bytearray(len(frame) // 3)
    pos = 0
    for i in range(0, len(frame), 3):
        out[pos] = palette_index[(frame[i], frame[i + 1], frame[i + 2])]
        pos += 1
    return bytes(out)


def lzw_encode(indices: bytes, min_code_size: int) -> bytes:
    clear_code = 1 << min_code_size
    end_code = clear_code + 1
    next_code = end_code + 1
    code_size = min_code_size + 1
    dictionary = {bytes([i]): i for i in range(clear_code)}
    out = bytearray()
    bit_buffer = 0
    bit_count = 0

    def emit(code: int) -> None:
        nonlocal bit_buffer, bit_count
        bit_buffer |= code << bit_count
        bit_count += code_size
        while bit_count >= 8:
            out.append(bit_buffer & 0xFF)
            bit_buffer >>= 8
            bit_count -= 8

    emit(clear_code)
    word = bytes([indices[0]])
    for value in indices[1:]:
        char = bytes([value])
        candidate = word + char
        if candidate in dictionary:
            word = candidate
            continue
        emit(dictionary[word])
        if next_code < 4096:
            dictionary[candidate] = next_code
            next_code += 1
            if next_code == (1 << code_size) and code_size < 12:
                code_size += 1
        word = char
    emit(dictionary[word])
    emit(end_code)
    if bit_count:
        out.append(bit_buffer & 0xFF)
    return bytes(out)


def lzw_encode_literal(indices: bytes, min_code_size: int) -> bytes:
    """Encode GIF pixels as literal codes with frequent clear-code resets.

    This is larger than a compressed stream, but it is deliberately simple and
    conservative so GitHub/browser decoders display it reliably.
    """
    clear_code = 1 << min_code_size
    end_code = clear_code + 1
    code_size = min_code_size + 1
    group_size = 8
    out = bytearray()
    bit_buffer = 0
    bit_count = 0

    def emit(code: int) -> None:
        nonlocal bit_buffer, bit_count
        bit_buffer |= code << bit_count
        bit_count += code_size
        while bit_count >= 8:
            out.append(bit_buffer & 0xFF)
            bit_buffer >>= 8
            bit_count -= 8

    for start in range(0, len(indices), group_size):
        emit(clear_code)
        for value in indices[start : start + group_size]:
            emit(value)
    emit(end_code)
    if bit_count:
        out.append(bit_buffer & 0xFF)
    return bytes(out)


def gif_subblocks(data: bytes) -> bytes:
    chunks = bytearray()
    for i in range(0, len(data), 255):
        part = data[i : i + 255]
        chunks.append(len(part))
        chunks.extend(part)
    chunks.append(0)
    return bytes(chunks)


def write_gif(frames: list[bytearray], path: Path, w: int, h: int, delay_cs: int = 50) -> None:
    palette, palette_index = palette_for_frames(frames)
    table_size = 2
    while table_size < len(palette):
        table_size *= 2
    table_size = max(2, table_size)
    min_code_size = max(2, (table_size - 1).bit_length())
    packed = 0b10000000 | 0b01110000 | ((table_size.bit_length() - 1) - 1)
    table = bytearray()
    for color in palette:
        table.extend(color)
    table.extend(b"\x00\x00\x00" * (table_size - len(palette)))

    data = bytearray()
    data.extend(b"GIF89a")
    data.extend(struct.pack("<HHBBB", w, h, packed, 0, 0))
    data.extend(table)
    data.extend(b"\x21\xFF\x0BNETSCAPE2.0\x03\x01\x00\x00\x00")
    for frame in frames:
        data.extend(b"\x21\xF9\x04")
        data.extend(struct.pack("<BHB", 0, delay_cs, 0))
        data.extend(b"\x00")
        data.extend(b"\x2C")
        data.extend(struct.pack("<HHHHB", 0, 0, w, h, 0))
        data.append(min_code_size)
        data.extend(gif_subblocks(lzw_encode_literal(frame_to_indices(frame, palette_index), min_code_size)))
    data.extend(b"\x3B")
    path.write_bytes(bytes(data))


SCREENSHOT_STEPS = (
    ("01-overview.png", "Overview", "The whole project flow: CSV data becomes a model, Flask serves it, and the dashboard demonstrates it."),
    ("02-dataset.png", "Dataset", "The task labels in data/tasks.csv teach the classifier the difference between High, Medium, and Low priority work."),
    ("03-training.png", "Training", "train.py cleans text, builds TF-IDF features, trains Logistic Regression, and writes model.joblib."),
    ("04-api.png", "API", "app.py exposes /health and /predict. The prediction route validates JSON, calls the model, and returns priority plus confidence."),
    ("05-dashboard.png", "Dashboard prediction", "Phase 1 lets the presenter type a task and see the live model response in the browser."),
    ("06-phase-2-load-test.png", "Phase 2 load test", "The load-test builder targets the local API by default. Private curls can be pasted locally during the live demo without committing them."),
    ("07-phase-3-tests.png", "Phase 3 tests", "Self-healing tests pass on the original API and on a mutated API that returns level/score instead of priority/confidence."),
    ("08-github-assets.png", "GitHub assets", "The repo includes a PPT, a GitHub-viewable GIF, this DEMO.md walkthrough, and screenshot panels."),
)


def write_screenshots() -> None:
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    w, h = 640, 360
    for scene, (filename, _title, _description) in enumerate(SCREENSHOT_STEPS):
        write_png(scene_frame(scene, 5, 6, w, h), SCREENSHOTS_DIR / filename, w, h)


def write_video() -> None:
    w, h, fps = 640, 360, 2
    frames: list[bytearray] = []
    ticks_per_scene = 6
    for scene in range(8):
        for tick in range(ticks_per_scene):
            frames.append(scene_frame(scene, tick, ticks_per_scene, w, h))
    write_gif(frames, GIF_PATH, w, h, delay_cs=int(100 / fps))


def write_demo_markdown() -> None:
    sections = [
        "# Smart Todo Demo Walkthrough",
        "",
        "This file is designed to render directly in GitHub. The animated walkthrough below replaces the old AVI file because GIF previews work inside GitHub markdown.",
        "",
        "![Smart Todo demo flow](smart-todo-demo-flow.gif)",
        "",
        "## Phase 2 Request Safety",
        "",
        "Do not commit private curl commands, bearer tokens, or internal service URLs. For the live demo, paste any private request directly into the dashboard curl parser on your machine.",
        "",
        "## Screenshots And Explanation",
        "",
    ]
    for filename, title, description in SCREENSHOT_STEPS:
        sections.extend(
            [
                f"### {title}",
                "",
                f"![{title}](screenshots/{filename})",
                "",
                description,
                "",
            ]
        )
    DEMO_MD_PATH.write_text("\n".join(sections), encoding="utf-8")


def write_demo_script() -> None:
    SCRIPT_PATH.write_text(
        """# Smart Todo Demo Script

## Run

```bash
cd /Users/ams/Desktop/simpleAiModel
.venv/bin/python app.py
```

Open: http://127.0.0.1:5000/

## Demo Order

1. Open `data/tasks.csv` and show labeled examples.
2. Open `train.py` and explain TF-IDF plus Logistic Regression.
3. Open `app.py` and explain `/health` and `/predict`.
4. Open the dashboard and try:
   - `Resolve P0 incident on checkout API`
   - `Prepare quarterly business review deck`
   - `Read newsletter from cloud provider`
5. Run Phase 3 tests from the dashboard:
   - `Run tests (original API)`
   - `Run tests (mutated API -> :5001)`
6. Mention Phase 2 load testing requires `k6`; show `reports/analysis.md` if k6 is not installed.
   If you need to demo a private API, paste that curl only during the live demo
   and keep private URLs or tokens out of committed files.

## Closing Line

This project demonstrates the full mini lifecycle of an AI API: dataset, training,
serving, dashboard interaction, performance-test hooks, and resilient API tests.
""",
        encoding="utf-8",
    )


def main() -> None:
    DEMO_DIR.mkdir(exist_ok=True)
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    write_pptx()
    write_video()
    write_screenshots()
    write_demo_markdown()
    write_demo_script()
    print(f"wrote {PPTX_PATH.relative_to(ROOT)}")
    print(f"wrote {GIF_PATH.relative_to(ROOT)}")
    print(f"wrote {DEMO_MD_PATH.relative_to(ROOT)}")
    print(f"wrote {SCRIPT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
