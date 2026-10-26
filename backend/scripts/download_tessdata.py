"""
Tải dữ liệu ngôn ngữ OCR (Tesseract traineddata) cho PyMuPDF.

PyMuPDF đã nhúng sẵn engine Tesseract, chỉ cần các file *.traineddata.
Script tải về thư mục ``backend/tessdata`` — LocalOCREngine tự tìm thấy.

Usage:
    python scripts/download_tessdata.py                 # vie + eng, chất lượng cao cho OCR tiếng Việt
    python scripts/download_tessdata.py --fast          # bản "fast", nhẹ hơn nhưng kém chính xác hơn
    python scripts/download_tessdata.py --langs vie eng osd
    python scripts/download_tessdata.py --dest /opt/tessdata

Trên Render: thêm vào Build Command
    pip install -r requirements.txt && python scripts/download_tessdata.py
"""

import argparse
import sys
import urllib.request
from pathlib import Path

# Windows consoles may default to CP1258, which cannot render several
# Vietnamese characters used in this script's help and progress messages.
# Make the maintenance command usable before it attempts any download.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

DEFAULT_DEST = Path(__file__).resolve().parents[1] / "tessdata"
REPOS = {
    "best": "https://github.com/tesseract-ocr/tessdata_best/raw/main/{lang}.traineddata",
    "fast": "https://github.com/tesseract-ocr/tessdata_fast/raw/main/{lang}.traineddata",
}


def download(lang: str, dest: Path, variant: str, force: bool) -> None:
    target = dest / f"{lang}.traineddata"
    # Avoid treating an already checked-in tessdata_fast file as the requested
    # high-quality model.  The fast English/Vietnamese files are much smaller
    # than their ``best`` equivalents, so replace them on the first default run.
    min_expected_bytes = 8 * 1024 * 1024 if variant == "best" else 1
    if target.exists() and target.stat().st_size >= min_expected_bytes and not force:
        print(f"[skip] {target} already exists")
        return

    if target.exists() and not force:
        print(f"[upgrade] replacing small {target.name} with tessdata_{variant}")

    url = REPOS[variant].format(lang=lang)
    print(f"[download] {url}")
    tmp = target.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=120) as response, open(tmp, "wb") as fh:
        while chunk := response.read(1 << 16):
            fh.write(chunk)
    tmp.replace(target)
    print(f"[ok] {target} ({target.stat().st_size / 1024 / 1024:.1f} MB)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--langs", nargs="+", default=["vie", "eng"])
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--fast", action="store_true", help="dùng tessdata_fast, nhanh hơn nhưng giảm độ chính xác")
    parser.add_argument("--best", action="store_true", help="dùng tessdata_best (mặc định)")
    parser.add_argument("--force", action="store_true", help="tải lại kể cả khi đã có")
    args = parser.parse_args()

    args.dest.mkdir(parents=True, exist_ok=True)
    # The Vietnamese fast model is only about 0.5 MB and is noticeably weak on
    # accents, low-contrast phone scans, and unfamiliar page layouts. Accuracy
    # is the safe default; deployments with tight CPU/RAM limits can opt into
    # --fast explicitly.
    variant = "fast" if args.fast else "best"
    try:
        for lang in args.langs:
            download(lang, args.dest, variant, args.force)
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
