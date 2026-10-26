"""Recognize photographed pages even when an old, invisible OCR layer exists."""

import fitz


def has_hidden_scan_text(page: fitz.Page) -> bool:
    if not page.get_images():
        return False
    traces = page.get_texttrace()
    hidden = sum(len(s.get("chars", ())) for s in traces
                 if s["type"] == 3 or s.get("opacity", 1) == 0)
    visible = sum(len(s.get("chars", ())) for s in traces
                  if s["type"] != 3 and s.get("opacity", 1) > 0)
    return hidden >= 40 and visible < 40


def photo_regions(page: fitz.Page) -> list[fitz.Rect]:
    """Crop separate photos only when no meaningful visible text is outside them.

    Overlapping tiles, small illustrations and genuine text PDFs retain their
    complete layout. Invisible OCR is not authoritative source content.
    """
    traces = page.get_texttrace()
    if sum(len(s.get("chars", ())) for s in traces
           if s["type"] != 3 and s.get("opacity", 1) > 0) >= 40:
        return []
    infos = page.get_image_info()
    if not infos or len(infos) > 4:
        return []
    rects = [fitz.Rect(info["bbox"]) & page.rect for info in infos]
    if any(r.is_empty or r.get_area() < page.rect.get_area() * .12
           or min(info["width"], info["height"]) < 400
           for r, info in zip(rects, infos)):
        return []
    for i, rect in enumerate(rects):
        if any((rect & other).get_area() > min(rect.get_area(), other.get_area()) * .02
               for other in rects[i + 1:]):
            return []
    return sorted(rects, key=lambda r: (round(r.y0 / 20), r.x0))
