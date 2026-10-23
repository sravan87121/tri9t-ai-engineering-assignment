"""Layout-aware native PDF extraction with Tesseract fallback; no LLM parsing."""

import hashlib
import re
import unicodedata
import fitz


def normalize(text):
    return " ".join(unicodedata.normalize("NFKC", text).split())


def digest(text):
    return hashlib.sha256(normalize(text).encode()).hexdigest()


def parent_number(number, known):
    parts = number.split(".")[:-1]
    while parts:
        candidate = ".".join(parts)
        if candidate in known:
            return candidate
        parts.pop()
    return "root"


def parse_pdf(path, force_ocr=False):
    nodes = [
        dict(
            key="root",
            parent=None,
            title="",
            kind="document",
            text="",
            page=1,
            blocks=[],
        )
    ]
    known = {"root": nodes[0]}
    current = nodes[0]
    warnings = []
    with fitz.open(path) as doc:
        for page_no, page in enumerate(doc, 1):
            ocr = force_ocr or len(page.get_text().strip()) < 20
            tp = page.get_textpage_ocr(dpi=300, full=True) if ocr else None
            if ocr:
                warnings.append(
                    f"Page {page_no}: OCR used; heading/table review required"
                )
            for block in page.get_text("dict", textpage=tp, sort=True)["blocks"]:
                if block["type"] == 1:
                    current["blocks"].append(
                        dict(
                            kind="figure",
                            page=page_no,
                            bbox=block["bbox"],
                            image_sha256=hashlib.sha256(block["image"]).hexdigest(),
                        )
                    )
                    continue
                lines = block.get("lines", [])
                text = normalize(
                    " ".join("".join(s["text"] for s in l["spans"]) for l in lines)
                )
                if not text:
                    continue
                match = re.match(r"^(\d+(?:\.\d+)*)(?:\.)?\s+(.+)$", text)
                bold = any("Bold" in s["font"] for l in lines for s in l["spans"])
                # OCR fallback: hierarchical numbering or an isolated short top-level heading.
                heading = match and (
                    bold or (ocr and ("." in match[1] or len(text) < 65))
                )
                if heading:
                    key, title = match.groups()
                    if key in known:
                        raise ValueError(
                            f"Duplicate section number {key}; manual resolution required"
                        )
                    parent = parent_number(key, known)
                    if key.count(".") and parent != key.rsplit(".", 1)[0]:
                        warnings.append(
                            f"{key}: missing immediate parent; attached to {parent}"
                        )
                    current = dict(
                        key=key,
                        parent=parent,
                        title=title,
                        kind="section",
                        text="",
                        page=page_no,
                        blocks=[],
                    )
                    nodes.append(current)
                    known[key] = current
                else:
                    kind = "list" if re.match(r"^\d+[.)]\s", text) else "paragraph"
                    if re.match(r"^(Figure|Fig\.)\s", text):
                        kind = "caption"
                    spans = [s for l in lines for s in l["spans"]]
                    # Preserve cells and geometry instead of guessing merged table boundaries.
                    if len(lines) > 1 and any(
                        abs(lines[i]["bbox"][1] - lines[i - 1]["bbox"][1]) < 3
                        for i in range(1, len(lines))
                    ):
                        kind = "table_row"
                    current["blocks"].append(
                        dict(
                            kind=kind,
                            text=text,
                            page=page_no,
                            bbox=block["bbox"],
                            cells=(
                                [normalize(s["text"]) for s in spans]
                                if kind == "table_row"
                                else None
                            ),
                        )
                    )
                    current["text"] += " " + text
        nodes[0]["title"] = nodes[0]["text"].strip()
    for n in reversed(nodes):
        children = [c for c in nodes if c["parent"] == n["key"]]
        n["text"] = normalize(n["text"])
        n["full_text"] = normalize(
            n["title"]
            + " "
            + n["text"]
            + " "
            + " ".join(c["full_text"] for c in children)
        )
        n["hash"] = digest(n["full_text"])
    return nodes, warnings
