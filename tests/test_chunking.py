"""Tests of the two chunking strategies on a hand-built parser output (no Spark, no workspace)."""

import json

import pytest

from evidence_curator.chunking import (
    BASELINE,
    SECTIONS,
    chunk_document,
    clean_text,
    element_chunks,
    element_type_counts,
    estimate_tokens,
    length_stats,
    overlap_tail,
    pack_sentences,
    parse_elements,
    section_chunks,
    table_chunks,
    table_to_text,
)


def _element(idx: int, kind: str, content: str, page: int = 0) -> dict:
    return {
        "bbox": [{"coord": [0, 0, 1, 1], "page_id": page}],
        "content": content,
        "description": None,
        "id": idx,
        "type": kind,
    }


METHODS = (
    "Participants were randomly assigned in a 2:1 ratio to once-weekly subcutaneous semaglutide or placebo. "
    "The primary end points were the percentage change in body weight from baseline to week 68 and the "
    "achievement of a weight reduction of at least 5%. Randomisation was stratified by region and by "
    "glycaemic status (prediabetes or normoglycaemia) at screening. Treatment was initiated at 0.25 mg per "
    "week and escalated every 4 weeks to the maintenance dose of 2.4 mg by week 16. Participants who could "
    "not tolerate the maintenance dose could remain on a lower dose. All analyses of the primary end points "
    "used the treatment policy estimand, which counts data regardless of discontinuation or rescue."
)

TABLE_HTML = (
    "<table><tr><th>End point</th><th>Semaglutide</th><th>Placebo</th></tr>"
    "<tr><td>Change in body weight, %</td><td>-14.9</td><td>-2.4</td></tr>"
    "<tr><td>Weight loss &ge;5%, n (%)</td><td>1047 (86.4)</td><td>182 (31.5)</td></tr></table>"
)

DOCUMENT = {
    "document": {
        "elements": [
            _element(0, "page_header", "n engl j med 384;11"),
            _element(1, "title", "Once-Weekly Semaglutide in Adults with Overweight or Obesity"),
            _element(2, "text", "J.P.H. Wilding, R.L. Batterham, and others, for the STEP 1 Study Group"),
            _element(3, "text", "Abstract: Obesity is a global health chal-\nlenge with few pharmacologic options."),
            _element(4, "section_header", "Methods"),
            _element(5, "text", METHODS),
            _element(6, "text", "Safety was assessed throughout."),
            _element(7, "section_header", "Results", page=1),
            _element(8, "table", TABLE_HTML, page=1),
            _element(9, "caption", "Table 1. Primary end points at week 68.", page=1),
            _element(10, "figure", "", page=1),
            _element(11, "page_footer", "1 of 14", page=1),
            _element(12, "section_header", "References", page=2),
            _element(13, "text", "1. Jensen MD, et al. Circulation 2014;129:S102-38.", page=2),
            _element(14, "text", "2. Bray GA, et al. Lancet 2016;387:1947-56.", page=2),
        ]
    }
}


def test_parse_elements_keeps_every_element_with_type_and_page() -> None:
    """All element types are kept in order, with the first bounding box's page."""
    elements = parse_elements(json.dumps(DOCUMENT))

    assert [e.type for e in elements][:5] == ["page_header", "title", "text", "text", "section_header"]
    assert elements[8].page == 1 and elements[0].page == 0
    assert elements[10].content == ""  # a figure without text content is kept, with empty content
    assert element_type_counts(elements) == {
        "text": 6,
        "section_header": 3,
        "caption": 1,
        "figure": 1,
        "page_footer": 1,
        "page_header": 1,
        "table": 1,
        "title": 1,
    }


def test_clean_text_repairs_hyphenation_and_whitespace_like_the_course() -> None:
    """The course's cleanup: hyphenation across line breaks repaired, whitespace collapsed, no stop-word removal."""
    assert clean_text("global health chal-\nlenge with  few\n options.") == "global health challenge with few options."
    assert clean_text("  \n ") == ""


def test_element_chunks_is_one_chunk_per_text_element() -> None:
    """The baseline keeps only `text` elements, one chunk each, so reference entries and headers come along."""
    chunks = element_chunks(parse_elements(DOCUMENT))

    assert [c.element_ids for c in chunks] == [[2], [3], [5], [6], [13], [14]]
    assert chunks[1].text.endswith("challenge with few pharmacologic options.")
    assert chunks[1].section == "Once-Weekly Semaglutide in Adults with Overweight or Obesity"
    assert chunks[2].section == "Methods" and chunks[4].section == "References"
    assert chunks[3].text == "Safety was assessed throughout."  # a fragment the baseline cannot avoid
    assert chunk_document(json.dumps(DOCUMENT), BASELINE) == chunks


def test_section_chunks_merges_paragraphs_splits_long_ones_and_skips_references() -> None:
    """Paragraphs under one heading are packed to the budget, long ones split at sentences, boilerplate skipped."""
    chunks = section_chunks(parse_elements(DOCUMENT), max_chars=600, overlap_chars=150, min_chars=60)

    sections = [c.section for c in chunks]
    assert "References" not in sections, "the reference list must not become retrieval material"
    assert all(c.n_chars <= 600 for c in chunks if c.kind == "text")
    # Preamble: author line and abstract merged under the title.
    assert chunks[0].element_ids == [2, 3] and chunks[0].section.startswith("Once-Weekly")
    # Methods: the long paragraph is split at sentence ends and the short paragraph is appended, not orphaned.
    methods = [c for c in chunks if c.section == "Methods"]
    assert len(methods) >= 2
    assert methods[0].text.startswith("Participants were randomly assigned")
    assert methods[-1].text.endswith("Safety was assessed throughout.")
    # Overlap: the second Methods chunk starts with the last sentence(s) of the first.
    tail = overlap_tail(methods[0].text, 150)
    assert tail and methods[1].text.startswith(tail)
    assert methods[1].element_ids[0] == 5
    assert len(methods) == 2 and methods[1].element_ids == [5, 6]  # the short paragraph joined the running buffer
    # Results: the table is a chunk of its own with cells joined, and its caption is attached to it.
    tables = [c for c in chunks if c.kind == "table"]
    assert len(tables) == 1 and tables[0].section == "Results" and tables[0].page == 1
    assert tables[0].text.splitlines()[:2] == [
        "Table 1. Primary end points at week 68.",
        "End point | Semaglutide | Placebo",
    ]
    assert "Weight loss ≥5%, n (%) | 1047 (86.4) | 182 (31.5)" in tables[0].text
    assert tables[0].element_ids == [8, 9]
    assert not [c for c in chunks if c.section == "Results" and c.kind == "text"]
    assert [c.seq for c in chunks] == list(range(len(chunks)))
    assert chunk_document(DOCUMENT, SECTIONS, max_chars=600, overlap_chars=150, min_chars=60) == chunks


def test_section_chunks_keeps_a_hard_character_cap_when_overlap_would_not_fit() -> None:
    """With a tight budget the carried overlap is shed sentence by sentence so no chunk exceeds the cap."""
    chunks = section_chunks(parse_elements(DOCUMENT), max_chars=400, overlap_chars=120, min_chars=60)

    assert all(c.n_chars <= 400 for c in chunks)
    assert [c.element_ids for c in chunks if c.section == "Methods"] == [[5], [5, 6]]


def test_caption_before_a_table_is_attached_to_every_piece_of_it() -> None:
    """A "Table n." line read just before its table is folded into the table chunks, repeated per piece."""
    rows = "".join(f"<tr><td>Row {i}</td><td>{i * 1.5:.1f}</td><td>{i * 2}</td></tr>" for i in range(1, 25))
    document = {
        "document": {
            "elements": [
                _element(0, "section_header", "Results"),
                _element(1, "caption", "Table 3. Secondary end points."),
                _element(2, "table", f"<table><tr><th>End point</th><th>A</th><th>B</th></tr>{rows}</table>"),
                _element(3, "text", "Secondary end points favoured treatment."),
            ]
        }
    }
    chunks = section_chunks(parse_elements(document), max_chars=300, min_chars=10)

    tables = [c for c in chunks if c.kind == "table"]
    assert len(tables) > 1 and all(
        c.text.startswith("Table 3. Secondary end points.\nEnd point | A | B") for c in tables
    )
    assert all(c.element_ids == [1, 2] and c.n_chars <= 300 for c in tables)
    assert [c.text for c in chunks if c.kind == "text"] == ["Secondary end points favoured treatment."]


def test_section_chunks_without_tables_and_with_custom_skip_list() -> None:
    """Tables can be left out, and the skip list is configurable."""
    chunks = section_chunks(parse_elements(DOCUMENT), include_tables=False, skip_sections=("methods",))

    assert all(c.kind == "text" for c in chunks)
    assert "Methods" not in {c.section for c in chunks}
    assert "References" in {c.section for c in chunks}


def test_pack_sentences_and_overlap_tail_respect_budgets() -> None:
    """Long text is cut at sentence ends under the budget; a run-on sentence is hard-cut; the tail is whole sentences."""
    pieces = pack_sentences(METHODS, 300)
    assert all(len(p) <= 300 for p in pieces) and " ".join(pieces) == METHODS
    assert pack_sentences("short", 300) == ["short"]
    assert pack_sentences("x" * 650, 300) == ["x" * 300, "x" * 300, "x" * 50]
    assert overlap_tail("One sentence. Two sentence. Three sentence.", 30) == "Two sentence. Three sentence."
    assert overlap_tail("One sentence.", 0) == ""


def test_table_to_text_and_table_chunks_repeat_the_header() -> None:
    """HTML tables become header-first rows; long tables split into pieces that each start with the header."""
    rows = table_to_text(TABLE_HTML)
    assert rows[0] == "End point | Semaglutide | Placebo" and len(rows) == 3
    assert table_to_text("plain text table") == ["plain text table"]
    pieces = table_chunks(rows, max_chars=90)
    assert len(pieces) == 2 and all(p.startswith("End point | Semaglutide | Placebo") for p in pieces)
    assert table_chunks([], 100) == []


def test_unknown_strategy_is_rejected() -> None:
    """Only the two named strategies exist."""
    with pytest.raises(ValueError, match="Unknown chunking strategy"):
        chunk_document(DOCUMENT, "semantic")


def test_length_stats_and_token_estimate() -> None:
    """Distribution summary with a limit count; the token estimate is the four-characters rule."""
    stats = length_stats([10, 20, 30, 40, 1000], limit=100)
    assert stats["count"] == 5 and stats["min"] == 10 and stats["max"] == 1000 and stats["p50"] == 30
    assert stats["over_limit"] == 1 and stats["mean"] == 220.0
    assert length_stats([])["count"] == 0
    assert estimate_tokens("MLOps is awesome") == 4
