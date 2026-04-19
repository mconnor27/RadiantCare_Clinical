"""Runtime helpers for PHI_MODE UI gating.

All helpers are no-ops when PHI_MODE is off, so pages can call them
unconditionally without branching.
"""

from __future__ import annotations

from config.settings import PHI_MODE

# Column field names that must be dropped from every grid in PHI_MODE.
# Kept broad — includes every variant we hash/drop during sanitization,
# so a page doesn't have to know which exact name its dataset uses.
PHI_HIDDEN_COLUMNS: set[str] = {
    # Patient identity
    "PatientFullName", "PatientName", "PatientId", "PatientMRN", "MRN",
    # Birth / demographics that persist in raw columns
    "DateOfBirth", "DOB",
    # Home address components
    "PatientAddressLine1", "PatientAddressLine2",
    # Free-text clinical notes (risk of embedded names)
    "AppointmentNotes", "ActivityNote", "ExamNotes", "PatientOutcome",
    "AppointmentNote",
    # Display-only column names used in derived grids
    "Patient Name", "Patient",
    "_patient_display",
}

# Columns that KEEP free-text filtering enabled in PHI_MODE.
# Everything else has its filter suppressed to prevent patient drill-down.
PHI_FILTERABLE_ALLOWLIST: set[str] = {
    "CourseId", "CourseName",
    "PlanSetupId", "PlanName", "PlanNames",
    # The Patient Code column shown on CPT / OTV Audit grids — users need
    # to be able to search for a specific code they're investigating.
    "PatientCode",
}


def filter_phi_columns(col_defs):
    """Remove PHI columns from an AG Grid columnDefs list when PHI_MODE is on.

    Returns the input unchanged when PHI_MODE is off.
    """
    if not PHI_MODE or not col_defs:
        return col_defs
    return [c for c in col_defs if _field_of(c) not in PHI_HIDDEN_COLUMNS]


def restrict_column_filters(col_defs):
    """Disable free-text column filters in PHI_MODE except for allowlisted columns.

    Returns the input unchanged when PHI_MODE is off.
    """
    if not PHI_MODE or not col_defs:
        return col_defs
    out = []
    for c in col_defs:
        cc = dict(c)
        field = _field_of(cc)
        if field not in PHI_FILTERABLE_ALLOWLIST:
            cc["filter"] = False
            cc["floatingFilter"] = False
        out.append(cc)
    return out


def apply_phi_grid_rules(col_defs):
    """Convenience: both filter_phi_columns and restrict_column_filters.

    Call once on any AG Grid columnDefs list; no-op when PHI_MODE is off.
    """
    return restrict_column_filters(filter_phi_columns(col_defs))


def _field_of(col_def) -> str:
    """Return the 'field' attribute of a column def, handling non-dict entries."""
    if isinstance(col_def, dict):
        return col_def.get("field", "") or ""
    return getattr(col_def, "field", "") or ""
