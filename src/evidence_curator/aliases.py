"""Drug alias mapping: the vocabulary bridge between questions, papers and registry records.

A user asks about "Wegovy", a paper says "semaglutide 2.4 mg", the registry lists "NN9535" as an
other name. The alias table maps every spelling to one canonical therapy, so a question phrased in
one vocabulary retrieves records stored in another. It is hand-built and small on purpose: every row
is a verified fact, and the agent joins through it rather than guessing.
"""

import re
from dataclasses import dataclass

from evidence_curator.seed import LIRAGLUTIDE, SEMAGLUTIDE, TIRZEPATIDE


@dataclass(frozen=True)
class DrugAlias:
    """One alias of a therapy."""

    therapy: str  # canonical name
    alias: str
    alias_type: str  # inn | brand | sponsor_code | dose_label | mechanism


DRUG_ALIASES: tuple[DrugAlias, ...] = (
    DrugAlias(SEMAGLUTIDE, "semaglutide", "inn"),
    DrugAlias(SEMAGLUTIDE, "semaglutide 2.4 mg", "dose_label"),
    DrugAlias(SEMAGLUTIDE, "semaglutide 7.2 mg", "dose_label"),
    DrugAlias(SEMAGLUTIDE, "Wegovy", "brand"),
    DrugAlias(SEMAGLUTIDE, "Ozempic", "brand"),
    DrugAlias(SEMAGLUTIDE, "NN9535", "sponsor_code"),
    DrugAlias(SEMAGLUTIDE, "GLP-1 receptor agonist", "mechanism"),
    DrugAlias(TIRZEPATIDE, "tirzepatide", "inn"),
    DrugAlias(TIRZEPATIDE, "Zepbound", "brand"),
    DrugAlias(TIRZEPATIDE, "Mounjaro", "brand"),
    DrugAlias(TIRZEPATIDE, "LY3298176", "sponsor_code"),
    DrugAlias(TIRZEPATIDE, "GIP/GLP-1 receptor agonist", "mechanism"),
    DrugAlias(LIRAGLUTIDE, "liraglutide", "inn"),
    DrugAlias(LIRAGLUTIDE, "liraglutide 3.0 mg", "dose_label"),
    DrugAlias(LIRAGLUTIDE, "liraglutide 3 mg", "dose_label"),
    DrugAlias(LIRAGLUTIDE, "Saxenda", "brand"),
    DrugAlias(LIRAGLUTIDE, "Victoza", "brand"),
    DrugAlias(LIRAGLUTIDE, "NN2211", "sponsor_code"),
    DrugAlias(LIRAGLUTIDE, "GLP-1 receptor agonist", "mechanism"),
)

_DOSE = re.compile(r"\s*\d+(\.\d+)?\s*mg\b.*$", flags=re.IGNORECASE)


def canonical_therapy(name: str) -> str | None:
    """Map any alias (case-insensitive, with or without a dose suffix) to its canonical therapy.

    Mechanism aliases are deliberately not matched: "GLP-1 receptor agonist" names a class, not a
    therapy, so a lookup on it returns None rather than an arbitrary member of the class.

    >>> canonical_therapy("Wegovy")
    'semaglutide'
    >>> canonical_therapy("Semaglutide 2.4 mg")
    'semaglutide'
    >>> canonical_therapy("Placebo") is None
    True
    """
    if not name:
        return None
    lookup = {a.alias.casefold(): a.therapy for a in DRUG_ALIASES if a.alias_type != "mechanism"}
    key = name.strip().casefold()
    if key in lookup:
        return lookup[key]
    stripped = _DOSE.sub("", key).strip()
    return lookup.get(stripped)
