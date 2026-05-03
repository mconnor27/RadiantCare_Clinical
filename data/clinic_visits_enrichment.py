"""Pre-sanitization enrichment for the Clinic Visits dataset.

Lifts the visit-type classifier upstream of PHI removal so the categorical
signal (Consult / Follow-Up / Virtual / Other) survives sanitization. The
sanitize pipeline calls `enrich()` BEFORE dropping AppointmentNotes; the
sanitized CSV that ships to production already carries a precomputed
VisitType column.

Pages still fall back to running the classifier at load time when the
column is absent (e.g. raw-data dev mode), so the runtime contract is
unchanged.
"""

from __future__ import annotations

import re

import pandas as pd


_FOLLOWUP_RE = re.compile(r'follow[\s-]?up|re[\s-]?eval|followup|reeval', re.IGNORECASE)
_EXPLICIT_FOLLOWUP_RE = re.compile(
    r'\bphone\b|\btelephone\b|follow[\s-]?up|f/u|re[\s-]?eval|reeval', re.IGNORECASE
)
_CONTEXT_FOLLOWUP_RE = re.compile(r'review|discuss|go\s+over', re.IGNORECASE)
_NEW_PATIENT_RE = re.compile(r'working\s+chart|bookmarked', re.IGNORECASE)
_STANDARD_CONSULT_NAMES = {'Consult', 'Consult - Special request', 'Consult- ADD ON'}


def classify_visit_type(row) -> str:
    """Classify a visit as Consult / Follow-Up / Virtual / Other.

    Inputs: ActivityName, DurationMinutes, AppointmentNotes (free text).
    Output is a categorical string with no PHI.

    Decision tree (from legacy-logic.md):
      1. ActivityName = "Re-eval" or "Follow-Up" → Follow-Up
      2. Duration > 60 min → Consult
      3. Standard consult names → Consult, unless notes mention follow-up
      4. Virtual Consult/Follow Up:
         - <60 min: note keywords decide; default Follow-Up
         - =60 min: note keywords decide; default Consult
         - unknown duration: note keywords decide; default Consult
      5. Fallback → Other
    """
    activity_name = (
        str(row.get("ActivityName", "")).strip()
        if pd.notna(row.get("ActivityName")) else ""
    )
    name_lower = activity_name.lower()

    if name_lower == "follow-up" or "re-eval" in name_lower or "reeval" in name_lower:
        return "Follow-Up"

    duration = pd.to_numeric(row.get("DurationMinutes"), errors="coerce")
    notes = (
        str(row.get("AppointmentNotes", ""))
        if pd.notna(row.get("AppointmentNotes")) else ""
    )

    if pd.notna(duration) and duration > 60:
        return "Consult"

    if activity_name in _STANDARD_CONSULT_NAMES:
        if _FOLLOWUP_RE.search(notes):
            return "Follow-Up"
        return "Consult"

    if "virtual" in name_lower or "tele" in name_lower:
        if pd.notna(duration) and 0 < duration < 60:
            if _EXPLICIT_FOLLOWUP_RE.search(notes):
                return "Follow-Up"
            if _CONTEXT_FOLLOWUP_RE.search(notes):
                return "Follow-Up"
            if _NEW_PATIENT_RE.search(notes):
                return "Consult"
            return "Follow-Up"
        elif pd.notna(duration) and duration == 60:
            if _FOLLOWUP_RE.search(notes):
                return "Follow-Up"
            return "Consult"
        else:
            if _FOLLOWUP_RE.search(notes):
                return "Follow-Up"
            return "Virtual"

    if "consult" in name_lower:
        return "Consult"

    return "Other"


def enrich(df: pd.DataFrame, salt: str) -> pd.DataFrame:
    """Sanitize-time hook: add VisitType before AppointmentNotes is dropped.

    Idempotent — skips if VisitType already exists (e.g. an earlier run
    on the same incremental file). The salt argument is unused here but
    is part of the enrich-hook signature so identifier-derived enrichments
    can use it.
    """
    if "VisitType" in df.columns:
        return df
    if "ActivityName" not in df.columns:
        return df
    df["VisitType"] = df.apply(classify_visit_type, axis=1)
    return df
