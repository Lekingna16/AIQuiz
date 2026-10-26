"""Read a supplied PDF with the configured OCR provider; never write to the DB.

Usage: python -X utf8 scripts/inspect_scan.py source.pdf --pages 1 --output .scratch/read.txt
"""
import argparse
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fitz
from app.config import get_settings
from app.services.pdf_reader import DeepSeekPDFReader, GeminiPDFReader, PDFReadError, split_pdf_batches
from app.services.text_extractor import TextExtractor
from app.utils.question_parser import parse_questions_from_text


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--pages", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = args.source.read_bytes()
    if args.pages:
        with fitz.open(stream=data, filetype="pdf") as doc, fitz.open() as part:
            part.insert_pdf(doc, from_page=0, to_page=min(args.pages, len(doc)) - 1)
            data = part.tobytes()
    print("Visual OCR route:", TextExtractor.is_scan_only_pdf(data), flush=True)
    settings = get_settings()
    if settings.OCR_PROVIDER == "deepseek":
        reader = DeepSeekPDFReader(settings.DEEPSEEK_API_KEY, settings.DEEPSEEK_VISION_MODEL, executor=None)
    else:
        reader = GeminiPDFReader(settings.GEMINI_API_KEY, settings.GEMINI_MODEL)
    batches = split_pdf_batches(data, 1)
    print("Provider:", settings.OCR_PROVIDER, "batches:", len(batches), flush=True)

    async def progress(stage, **details):
        print(stage, details, flush=True)

    text = await reader.read(batches, progress)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    questions = parse_questions_from_text(text)
    print("Questions:", len(questions), "incomplete:", sum(len(q["options"]) != 4 for q in questions), flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except PDFReadError as error:
        sys.exit(str(error))
