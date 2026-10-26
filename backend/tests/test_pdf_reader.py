import asyncio
import base64
import json
from unittest.mock import AsyncMock

import fitz
import httpx
import pytest

from app.services.pdf_reader import GeminiPDFReader, PDFReadError, split_pdf_batches


def make_pdf(pages):
    with fitz.open() as doc:
        for number in range(pages):
            doc.new_page().insert_text((72, 72), f"Question {number + 1}")
        return doc.tobytes()


def reply(text, finish="STOP"):
    return httpx.Response(200, json={"candidates": [{
        "finishReason": finish, "content": {"parts": [{"text": text}]},
    }]})


def test_batches_preserve_every_page_without_rasterizing(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Must not rasterize PDF")

    monkeypatch.setattr(fitz.Page, "get_pixmap", forbidden)
    batches = split_pdf_batches(make_pdf(9))
    assert [(start, end) for start, end, _ in batches] == [(1, 4), (5, 8), (9, 9)]
    for start, end, data in batches:
        with fitz.open(stream=data, filetype="pdf") as part:
            assert len(part) == end - start + 1
            assert [p.get_text().strip() for p in part] == [
                f"Question {n}" for n in range(start, end + 1)
            ]


@pytest.mark.asyncio
async def test_reader_limits_concurrency_and_preserves_vietnamese_source_order():
    active = peak = 0
    second_finished = asyncio.Event()

    async def handler(request):
        nonlocal active, peak
        active += 1
        peak = max(active, peak)
        body = json.loads(request.content)
        inline = body["contents"][0]["parts"][0]["inlineData"]
        assert inline["mimeType"] == "application/pdf"
        with fitz.open(stream=base64.b64decode(inline["data"]), filetype="pdf") as doc:
            first = int(doc[0].get_text().strip().split()[-1])
        if first == 1:
            await asyncio.wait_for(second_finished.wait(), timeout=1)
        else:
            second_finished.set()
        active -= 1
        return reply(f"Câu {first}: Tràn dịch màng phổi?\nA. Mờ đồng nhất")

    progress = AsyncMock()
    reader = GeminiPDFReader("test-key", "test-model", transport=httpx.MockTransport(handler))
    text = await reader.read(split_pdf_batches(make_pdf(9)), progress)
    assert peak == 2
    assert text.index("Câu 1:") < text.index("Câu 5:") < text.index("Câu 9:")
    assert text.count("Mờ đồng nhất") == 3
    updates = [call.kwargs for call in progress.await_args_list]
    assert updates[-1] == {"completed_pages": 9, "total_pages": 9}
    counts = [0] + [u["completed_pages"] for u in updates]
    assert sorted(b - a for a, b in zip(counts, counts[1:])) == [1, 4, 4]


@pytest.mark.asyncio
@pytest.mark.parametrize("status, message", [(429, "quota"), (403, "API key"), (404, "GEMINI_MODEL")])
async def test_provider_configuration_errors_are_not_retried(status, message):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(status)

    reader = GeminiPDFReader("test-key", "test-model", transport=httpx.MockTransport(handler))
    with pytest.raises(PDFReadError, match=message):
        await reader.read(split_pdf_batches(make_pdf(1)), AsyncMock())
    assert calls == 1


@pytest.mark.asyncio
async def test_truncated_output_is_not_accepted_as_complete():
    reader = GeminiPDFReader("test-key", "test-model", transport=httpx.MockTransport(
        lambda request: reply("Câu 1: chưa đủ", "MAX_TOKENS")
    ))
    progress = AsyncMock()
    with pytest.raises(PDFReadError, match="chưa đọc hết"):
        await reader.read(split_pdf_batches(make_pdf(1)), progress)
    progress.assert_not_awaited()


def test_page_limit_fails_instead_of_silently_skipping_pages():
    with pytest.raises(PDFReadError, match="100 trang"):
        split_pdf_batches(make_pdf(101))
