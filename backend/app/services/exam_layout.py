"""Keep wrapped choices in their own columns before discarding PDF coordinates."""

import re

OPTION = re.compile(r"^\s*([A-D])(?:[.):]|\s)\s*\S", re.IGNORECASE)
BOUNDARY = re.compile(
    r"^\s*(?:(?:Câu|Cau|Question)\s*\d+|\d+\s*[.):]|"
    r"(?:Phần|Dữ kiện|Tình huống)\s+(?:câu|các câu)|Trang\s+\d+)",
    re.IGNORECASE,
)


def _text(line):
    return "".join("".join(c["c"] for c in span.get("chars", []))
                   for span in line.get("spans", []))


def order_exam_blocks(blocks: list[dict]) -> list[dict]:
    """Recognize aligned pairs of labelled choices and retain column continuations.

    Only unmistakable paired labels start a region. Other layouts keep the
    existing extraction order. Labels, characters and styling are never changed.
    """
    blocks = [{**block, "lines": sorted(block.get("lines", []),
                key=lambda line: (round(line["bbox"][1] / 4), line["bbox"][0]))}
              for block in blocks]
    lines = sorted((line for block in blocks for line in block.get("lines", [])),
                   key=lambda line: (round(line["bbox"][1] / 4), line["bbox"][0]))
    output = []
    changed = False
    i = 0
    while i < len(lines):
        left = lines[i]
        right = lines[i + 1] if i + 1 < len(lines) else None
        left_label = OPTION.match(_text(left))
        right_label = OPTION.match(_text(right)) if right else None
        height = max(1, left["bbox"][3] - left["bbox"][1])
        paired = (
            left_label and right_label
            and left_label[1].upper() != right_label[1].upper()
            and abs(left["bbox"][1] - right["bbox"][1]) < height * .7
            and right["bbox"][0] - left["bbox"][2] >= height
        )
        if not paired:
            output.append({"type": 0, "bbox": left["bbox"], "lines": [left]})
            i += 1
            continue

        right_x = right["bbox"][0]
        groups = []
        active = {}
        keys = set()
        cursor = i
        last_y = left["bbox"][1]
        while cursor < len(lines):
            line = lines[cursor]
            x0, y0, x1, _ = line["bbox"]
            text = _text(line)
            if BOUNDARY.match(text) or y0 - last_y > height * 3:
                break
            column = 1 if x0 >= right_x - height * .5 else 0
            # A full-width paragraph is outside the option grid.
            if column == 0 and x1 > right_x - height * .5:
                break
            label = OPTION.match(text)
            if label:
                key = label[1].upper()
                if key in keys:
                    break
                keys.add(key)
                group = [line]
                groups.append(group)
                active[column] = group
            elif column in active:
                # Continuations must align with the option text, not the next
                # full-width question heading at the page margin.
                anchor = active[column][0]["bbox"][0]
                if x0 < anchor - height * .5:
                    break
                active[column].append(line)
            else:
                break
            last_y = max(last_y, y0)
            cursor += 1

        if cursor < i + 2:
            output.append({"type": 0, "bbox": left["bbox"], "lines": [left]})
            i += 1
            continue

        grouped = [line for group in groups for line in group]
        output.append({
            "type": 0,
            "bbox": (min(l["bbox"][0] for l in grouped), min(l["bbox"][1] for l in grouped),
                     max(l["bbox"][2] for l in grouped), max(l["bbox"][3] for l in grouped)),
            "lines": grouped,
        })
        changed = True
        i = cursor
    return output if changed else blocks
