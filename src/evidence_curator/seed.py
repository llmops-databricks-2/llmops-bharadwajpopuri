"""The fixed trial snapshot: which ClinicalTrials.gov records the curator covers.

The project scope is one indication (obesity) and three therapies on a fixed snapshot of records.
A pinned list of NCT IDs makes the snapshot explicit and reproducible: re-running the job refreshes
the registry fields (status, enrollment, posted results) but never silently changes which trials are
in the dataset. The IDs were selected from ClinicalTrials.gov API v2 queries on
intervention + condition + lead sponsor + phase (2/3) and verified against the API on 2026-10-14.
"""

from dataclasses import dataclass

SEMAGLUTIDE = "semaglutide"
TIRZEPATIDE = "tirzepatide"
LIRAGLUTIDE = "liraglutide"


@dataclass(frozen=True)
class SeedTrial:
    """One pinned trial: the registry ID plus the curator's own labels for it."""

    nct_id: str
    therapy: str  # canonical therapy name (see evidence_curator.aliases)
    program: str  # clinical programme the trial belongs to, as the sponsor names it
    note: str  # why the trial is in the snapshot


SEED_TRIALS: tuple[SeedTrial, ...] = (
    # Semaglutide 2.4 mg once weekly (Novo Nordisk): the STEP programme and related trials
    SeedTrial("NCT03548935", SEMAGLUTIDE, "STEP", "STEP 1: pivotal phase 3 in obesity without T2D"),
    SeedTrial("NCT03552757", SEMAGLUTIDE, "STEP", "STEP 2: phase 3 in overweight/obesity with T2D"),
    SeedTrial("NCT03611582", SEMAGLUTIDE, "STEP", "STEP 3: phase 3 with intensive behavioural therapy"),
    SeedTrial("NCT03548987", SEMAGLUTIDE, "STEP", "STEP 4: phase 3 withdrawal/maintenance design"),
    SeedTrial("NCT03693430", SEMAGLUTIDE, "STEP", "STEP 5: two-year phase 3"),
    SeedTrial("NCT03811574", SEMAGLUTIDE, "STEP", "STEP 6: phase 3 in East Asian participants"),
    SeedTrial("NCT04074161", SEMAGLUTIDE, "STEP", "STEP 8: phase 3 head-to-head versus liraglutide 3.0 mg"),
    SeedTrial("NCT04102189", SEMAGLUTIDE, "STEP", "STEP TEENS: phase 3 in adolescents"),
    SeedTrial("NCT05646706", SEMAGLUTIDE, "STEP", "STEP UP: phase 3 of the 7.2 mg dose"),
    SeedTrial("NCT05726227", SEMAGLUTIDE, "STEP", "STEP Young: phase 3 in children, not yet reported"),
    SeedTrial("NCT03574597", SEMAGLUTIDE, "SELECT", "SELECT: cardiovascular outcomes trial in overweight/obesity"),
    SeedTrial("NCT02453711", SEMAGLUTIDE, "PHASE2", "Phase 2 dose-finding of once-daily semaglutide in obesity"),
    # Tirzepatide (Eli Lilly): the SURMOUNT programme and related trials
    SeedTrial("NCT04184622", TIRZEPATIDE, "SURMOUNT", "SURMOUNT-1: pivotal phase 3 in obesity without T2D"),
    SeedTrial("NCT04657003", TIRZEPATIDE, "SURMOUNT", "SURMOUNT-2: phase 3 in obesity with T2D"),
    SeedTrial("NCT04657016", TIRZEPATIDE, "SURMOUNT", "SURMOUNT-3: phase 3 after a lifestyle lead-in"),
    SeedTrial("NCT04660643", TIRZEPATIDE, "SURMOUNT", "SURMOUNT-4: phase 3 withdrawal/maintenance design"),
    SeedTrial("NCT05822830", TIRZEPATIDE, "SURMOUNT", "SURMOUNT-5: phase 3 head-to-head versus semaglutide 2.4 mg"),
    SeedTrial("NCT05412004", TIRZEPATIDE, "SURMOUNT", "SURMOUNT-OSA: phase 3 in obstructive sleep apnoea"),
    SeedTrial("NCT04844918", TIRZEPATIDE, "SURMOUNT", "SURMOUNT-J: phase 3 in Japanese participants"),
    SeedTrial("NCT05556512", TIRZEPATIDE, "SURMOUNT", "SURMOUNT-MMO: ongoing morbidity/mortality outcomes trial"),
    SeedTrial("NCT06439277", TIRZEPATIDE, "SURMOUNT", "Phase 3 in adolescents, recruiting"),
    # Liraglutide 3.0 mg once daily (Novo Nordisk): the SCALE programme and related trials
    SeedTrial("NCT01272219", LIRAGLUTIDE, "SCALE", "SCALE Obesity and Prediabetes: pivotal phase 3"),
    SeedTrial("NCT01272232", LIRAGLUTIDE, "SCALE", "SCALE Diabetes: phase 3 in overweight/obesity with T2D"),
    SeedTrial("NCT00781937", LIRAGLUTIDE, "SCALE", "SCALE Maintenance: phase 3 after diet-induced weight loss"),
    SeedTrial("NCT01557166", LIRAGLUTIDE, "SCALE", "SCALE Sleep Apnea: phase 3 in obstructive sleep apnoea"),
    SeedTrial("NCT02963922", LIRAGLUTIDE, "SCALE", "SCALE Insulin: phase 3 in T2D on basal insulin"),
    SeedTrial("NCT02963935", LIRAGLUTIDE, "SCALE", "SCALE IBT: phase 3 with intensive behavioural therapy"),
    SeedTrial("NCT02918279", LIRAGLUTIDE, "SCALE", "SCALE Teens: phase 3 in adolescents"),
    SeedTrial("NCT04775082", LIRAGLUTIDE, "SCALE", "SCALE KIDS: phase 3 in children, not yet reported"),
    SeedTrial("NCT00422058", LIRAGLUTIDE, "PHASE2", "Phase 2 dose-ranging of liraglutide in obesity"),
)


def seed_by_id() -> dict[str, SeedTrial]:
    """Index the seed list by NCT ID."""
    return {trial.nct_id: trial for trial in SEED_TRIALS}
