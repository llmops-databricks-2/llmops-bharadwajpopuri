"""Chunking: from `ai_parse_document` output to retrieval units, with two strategies to compare.

A chunk is what retrieval returns, so its boundaries decide what evidence the agent can quote. The
parser gives a flat list of elements (titles, section headers, paragraphs, captions, tables, page
furniture) in reading order; two ways of turning them into chunks live here:

- `element_chunks`, the course baseline: one chunk per `text` element, cleaned the way the course's
  `DataProcessor._clean_chunk` cleans (hyphenation repaired across line breaks, whitespace collapsed),
  everything else dropped. Predictable and cheap; the chunk sizes are whatever the parser's paragraphs
  happen to be, from a one-line fragment to a page-long paragraph, and tables are lost.
- `section_chunks`, the alternative: structural, section-aware packing. Consecutive paragraphs under
  the same heading are merged up to a character budget (with a sentence-aligned overlap carried into
  the next chunk), long paragraphs are split at sentence ends, page headers and footers are dropped,
  reference lists and other boilerplate sections are skipped, and tables become chunks of their own
  with the header row repeated in every piece. Each chunk records the section it came from.

Character lengths are what the code controls; the embedding model's own token count is measured in
the inspection notebook from the gateway's usage report. The rule of thumb used for planning is the
lecture's four characters per token.

Pure Python: the Spark side (reading `parsed_papers`, joining metadata, writing the chunk table) is
in the processing notebook.
"""

import html
import json
import re
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

BASELINE = "element"
SECTIONS = "section"
STRATEGIES = (BASELINE, SECTIONS)

# Defaults of the section strategy. 1,500 characters is about 375 tokens by the four-characters rule:
# a paragraph or two, well inside GTE Large's input window, and small enough that a question about one
# endpoint retrieves the passage that reports it rather than a whole results section.
MAX_CHARS = 1500
OVERLAP_CHARS = 200
MIN_CHARS = 120
SKIP_SECTIONS = ("references", "bibliography", "acknowledg", "author contributions", "data availability")
HEADING_TYPES = ("title", "section_header")
FURNITURE_TYPES = ("page_header", "page_footer")
BODY_TYPES = ("text", "caption", "footnote", "list_item")

CHARS_PER_TOKEN = 4

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")
_TAG = re.compile(r"<[^>]+>")
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class Element:
    """One element of a parsed document, in reading order."""

    id: int
    type: str
    content: str
    page: int | None


@dataclass
class Chunk:
    """One retrieval unit: text plus where it came from."""

    seq: int
    text: str
    element_ids: list[int] = field(default_factory=list)
    page: int | None = None
    section: str | None = None
    kind: str = "text"  # text | table

    @property
    def n_chars(self) -> int:
        """Length in characters, the unit the strategies control."""
        return len(self.text)

    @property
    def n_tokens_est(self) -> int:
        """Planning estimate of the token count (four characters per token); not the model's count."""
        return estimate_tokens(self.text)


def estimate_tokens(text: str) -> int:
    """Estimate tokens by the lecture's rule of thumb; the embedding model's tokenizer is the authority."""
    return max(1, round(len(text) / CHARS_PER_TOKEN))


def clean_text(text: str) -> str:
    r"""Clean a parsed element the way the course's `DataProcessor._clean_chunk` does.

    Hyphenation across line breaks is repaired ("docu-\nments" → "documents"), newlines and repeated
    whitespace collapse to single spaces. Stop words are not removed: the embedding model wants
    natural text.
    """
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text or "")
    t = re.sub(r"\s*\n\s*", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def parse_elements(parsed_content: str | dict[str, Any]) -> list[Element]:
    """Read the parser's JSON (the `parsed_content` string, or the already-decoded object) into elements.

    Every element is kept, whatever its type, so the inspection can count headers, tables and
    figures; the strategies decide what to use. The page is the first bounding box's `page_id`.
    """
    data = json.loads(parsed_content) if isinstance(parsed_content, str) else parsed_content
    elements: list[Element] = []
    for raw in (data.get("document") or {}).get("elements") or []:
        boxes = raw.get("bbox") or []
        page = boxes[0].get("page_id") if boxes and isinstance(boxes[0], dict) else None
        content = raw.get("content")
        elements.append(
            Element(
                id=int(raw.get("id", len(elements))),
                type=str(raw.get("type") or "unknown"),
                content=content if isinstance(content, str) else "",
                page=int(page) if page is not None else None,
            )
        )
    return elements


def element_type_counts(elements: Iterable[Element]) -> dict[str, int]:
    """How many elements of each type the parser produced (for the inspection report)."""
    counts: dict[str, int] = {}
    for element in elements:
        counts[element.type] = counts.get(element.type, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def element_chunks(elements: Sequence[Element], element_types: Sequence[str] = ("text",)) -> list[Chunk]:
    """Apply the course baseline: one chunk per `text` element, cleaned; empty elements dropped."""
    chunks: list[Chunk] = []
    section: str | None = None
    for element in elements:
        if element.type in HEADING_TYPES:
            section = clean_text(element.content) or section
            continue
        if element.type not in element_types:
            continue
        text = clean_text(element.content)
        if not text:
            continue
        chunks.append(Chunk(seq=len(chunks), text=text, element_ids=[element.id], page=element.page, section=section))
    return chunks


def split_sentences(text: str) -> list[str]:
    """Split at sentence ends followed by a capital, digit or bracket; abbreviations like "e.g. the" stay together."""
    return [s for s in _SENTENCE_END.split(text) if s]


def pack_sentences(text: str, max_chars: int) -> list[str]:
    """Cut a long paragraph into pieces of at most `max_chars`, at sentence ends where possible."""
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    current = ""
    for sentence in split_sentences(text):
        while len(sentence) > max_chars:  # a single run-on sentence longer than the budget: hard cut
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:max_chars])
            sentence = sentence[max_chars:].lstrip()
        if current and len(current) + 1 + len(sentence) > max_chars:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def overlap_tail(text: str, overlap_chars: int) -> str:
    """Take the last whole sentences of a chunk, up to `overlap_chars`, to carry into the next chunk."""
    if overlap_chars <= 0:
        return ""
    tail: list[str] = []
    length = 0
    for sentence in reversed(split_sentences(text)):
        if length + len(sentence) + 1 > overlap_chars:
            break
        tail.insert(0, sentence)
        length += len(sentence) + 1
    return " ".join(tail)


def table_to_text(content: str) -> list[str]:
    """Turn a parsed table into text rows ("cell | cell | cell"); HTML tables are read row by row.

    Returns the rows, header first, so the caller can split long tables and repeat the header.
    """
    rows = _ROW.findall(content or "")
    if not rows:
        text = clean_text(html.unescape(_TAG.sub(" ", content or "")))
        return [text] if text else []
    lines: list[str] = []
    for row in rows:
        cells = [clean_text(html.unescape(_TAG.sub(" ", cell))) for cell in _CELL.findall(row)]
        line = " | ".join(cell for cell in cells if cell)
        if line:
            lines.append(line)
    return lines


def table_chunks(lines: Sequence[str], max_chars: int) -> list[str]:
    """Split a table's rows into pieces under the budget, repeating the header row in each piece."""
    if not lines:
        return []
    header, body = lines[0], list(lines[1:])
    if not body:
        return [header[:max_chars]]
    pieces: list[str] = []
    current = header
    for row in body:
        candidate = f"{current}\n{row}"
        if len(candidate) > max_chars and current != header:
            pieces.append(current)
            current = f"{header}\n{row}"
        else:
            current = candidate
    pieces.append(current)
    return [piece[:max_chars] for piece in pieces]


_CAPTION = re.compile(r"^(table|fig\.?|figure|supplementary table)\s*[A-Za-z]?\d", re.IGNORECASE)


def _is_caption(text: str) -> bool:
    return len(text) <= 400 and bool(_CAPTION.match(text.split("\n", 1)[0]))


def _is_skipped(section: str | None, skip_sections: Sequence[str]) -> bool:
    heading = (section or "").casefold()
    return any(heading.startswith(marker) or f" {marker}" in heading for marker in skip_sections)


def section_chunks(
    elements: Sequence[Element],
    max_chars: int = MAX_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
    min_chars: int = MIN_CHARS,
    skip_sections: Sequence[str] = SKIP_SECTIONS,
    include_tables: bool = True,
) -> list[Chunk]:
    """Apply the alternative strategy: section-aware packing of consecutive paragraphs with sentence overlap.

    Args:
        elements: parsed elements in reading order.
        max_chars: budget per chunk; paragraphs longer than it are split at sentence ends.
        overlap_chars: how much of a chunk's tail (whole sentences) is repeated at the start of the next
            chunk of the same section, so a sentence cut by the boundary is still retrievable in full.
        min_chars: a buffer smaller than this at a section change is appended to the previous chunk of
            the section when it fits, instead of becoming a fragment.
        skip_sections: headings whose content is not retrieval material (reference lists and the like).
        include_tables: whether table elements become chunks (header row repeated in every piece).

    """
    chunks: list[Chunk] = []
    section: str | None = None
    skipping = False
    buffer: list[str] = []
    buffer_ids: list[int] = []
    buffer_page: int | None = None
    carried = ""  # overlap text carried into the next buffer; not counted as new element ids

    def flush(force_new: bool = False) -> None:
        nonlocal buffer, buffer_ids, buffer_page, carried
        if not buffer:  # nothing new since the last chunk: an overlap tail alone is not a chunk
            carried = ""
            return
        text = " ".join(part for part in ([carried] if carried else []) + buffer).strip()
        ids = list(buffer_ids)
        page = buffer_page
        previous = chunks[-1] if chunks else None
        if (
            not force_new
            and len(text) < min_chars
            and previous is not None
            and previous.section == section
            and previous.kind == "text"
            and len(previous.text) + 1 + len(text) <= max_chars + min_chars
        ):
            previous.text = f"{previous.text} {text}"
            previous.element_ids.extend(i for i in ids if i not in previous.element_ids)
        else:
            chunks.append(Chunk(seq=len(chunks), text=text, element_ids=ids, page=page, section=section))
        carried = ""
        buffer, buffer_ids, buffer_page = [], [], None

    for element in elements:
        if element.type in HEADING_TYPES:
            flush()
            carried = ""
            section = clean_text(element.content) or section
            skipping = _is_skipped(section, skip_sections)
            continue
        if element.type in FURNITURE_TYPES or skipping:
            continue
        if element.type == "table":
            if not include_tables:
                continue
            caption, caption_ids = "", []
            if len(buffer) == 1 and _is_caption(buffer[0]):  # "Table 2. ..." just before the table belongs to it
                caption, caption_ids = buffer[0], list(buffer_ids)
                buffer, buffer_ids, buffer_page, carried = [], [], None, ""
            flush()
            budget = max(max_chars - len(caption) - 1, max_chars // 2)
            for piece in table_chunks(table_to_text(element.content), budget):
                text = f"{caption}\n{piece}" if caption else piece
                chunks.append(
                    Chunk(
                        seq=len(chunks),
                        text=text,
                        element_ids=caption_ids + [element.id],
                        page=element.page,
                        section=section,
                        kind="table",
                    )
                )
            continue
        if element.type not in BODY_TYPES:
            continue
        text = clean_text(element.content)
        if not text:
            continue
        if (
            _is_caption(text)
            and chunks
            and chunks[-1].kind == "table"
            and not buffer
            and not _is_caption(chunks[-1].text)
        ):
            table_id = chunks[-1].element_ids[-1]  # a caption right after its table: attach to every piece of it
            for chunk in chunks:
                if chunk.kind == "table" and chunk.element_ids[-1] == table_id and chunk.section == section:
                    chunk.text = f"{text}\n{chunk.text}"
                    chunk.element_ids.append(element.id)
            continue
        for piece in pack_sentences(text, max_chars):
            current_len = len(carried) + sum(len(p) + 1 for p in buffer)
            if buffer and current_len + 1 + len(piece) > max_chars:
                flushed_text = " ".join(([carried] if carried else []) + buffer)
                flush(force_new=True)
                carried = overlap_tail(flushed_text, overlap_chars)
            if not buffer:  # the overlap must leave room for the new piece: shed its oldest sentences
                while carried and len(carried) + 1 + len(piece) > max_chars:
                    carried = " ".join(split_sentences(carried)[1:])
            buffer.append(piece)
            buffer_ids.append(element.id)
            if buffer_page is None:
                buffer_page = element.page
    flush()
    return chunks


def chunk_elements(elements: Sequence[Element], strategy: str, **settings: int | bool | Sequence[str]) -> list[Chunk]:
    """Chunk parsed elements with the named strategy (`element` or `section`)."""
    if strategy == BASELINE:
        return element_chunks(elements)
    if strategy == SECTIONS:
        return section_chunks(elements, **settings)
    raise ValueError(f"Unknown chunking strategy: {strategy!r} (expected one of {STRATEGIES})")


def chunk_document(
    parsed_content: str | dict[str, Any], strategy: str, **settings: int | bool | Sequence[str]
) -> list[Chunk]:
    """Chunk one parsed document (the `parsed_content` JSON) with the named strategy."""
    return chunk_elements(parse_elements(parsed_content), strategy, **settings)


def length_stats(lengths: Sequence[int], limit: int | None = None) -> dict[str, float | int | None]:
    """Count, min, median, p95, max and mean of a length distribution, and how many exceed a limit."""
    if not lengths:
        return {"count": 0, "min": None, "p50": None, "p95": None, "max": None, "mean": None, "over_limit": 0}
    ordered = sorted(lengths)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return {
        "count": len(ordered),
        "min": ordered[0],
        "p50": int(statistics.median(ordered)),
        "p95": p95,
        "max": ordered[-1],
        "mean": round(statistics.fmean(ordered), 1),
        "over_limit": sum(1 for n in ordered if limit is not None and n > limit),
    }
