"""Reusable AI Settings picker (model + thinking level).

Drop ``ai_settings_panel(prefix)`` into any layout where AI features are
launched; register the callbacks once via ``register_ai_settings_callbacks(prefix)``.
The pair persists choices via utils.ai_config (which writes to app_settings).
"""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import callback, Input, Output, no_update
from dash_iconify import DashIconify

from utils.ai_config import (
    DEFAULT_MODEL, DEFAULT_THINKING,
    get_model, get_thinking_level,
    model_options, thinking_options,
    set_model, set_thinking_level,
)


def ai_settings_panel(prefix: str, *, compact: bool = False) -> dmc.Accordion:
    """Collapsible panel with two Selects.

    ``prefix`` keeps IDs unique when the panel appears on multiple pages
    (e.g. ``"mob"`` for mobile, ``"bill"`` for billing modal).
    """
    cur_model = get_model() or DEFAULT_MODEL
    cur_think = get_thinking_level() or DEFAULT_THINKING
    size = "xs" if compact else "sm"
    return dmc.Accordion(
        chevronPosition="right",
        variant="separated",
        radius="md",
        children=[
            dmc.AccordionItem(value="ai", children=[
                dmc.AccordionControl(
                    dmc.Group(gap=6, children=[
                        DashIconify(icon="tabler:brain", width=14, color="#7C2A83"),
                        dmc.Text("AI Settings", size=size, fw=600),
                        dmc.Text(
                            id=f"{prefix}-ai-settings-summary",
                            size="xs", c="dimmed",
                        ),
                    ]),
                ),
                dmc.AccordionPanel(children=[
                    dmc.Stack(gap="xs", children=[
                        dmc.Select(
                            id=f"{prefix}-ai-model",
                            label="Model",
                            data=model_options(),
                            value=cur_model,
                            clearable=False, size=size,
                            leftSection=DashIconify(icon="tabler:cpu", width=12),
                        ),
                        dmc.Select(
                            id=f"{prefix}-ai-thinking",
                            label="Extended thinking",
                            data=thinking_options(),
                            value=cur_think,
                            clearable=False, size=size,
                            leftSection=DashIconify(icon="tabler:bulb", width=12),
                        ),
                        dmc.Text(
                            "Smarter models are slower and cost more. Higher thinking budgets give the model more reasoning room before answering. Applies to all AI features (diagnoses, payors, providers).",
                            size="xs", c="dimmed",
                        ),
                    ]),
                ]),
            ]),
        ],
    )


def register_ai_settings_callbacks(prefix: str) -> None:
    """Wire the two Selects to persist choices on every change."""

    @callback(
        Output(f"{prefix}-ai-settings-summary", "children"),
        Input(f"{prefix}-ai-model", "value"),
        Input(f"{prefix}-ai-thinking", "value"),
        prevent_initial_call=False,
    )
    def _persist_and_summarize(model_val, thinking_val):
        if model_val:
            set_model(model_val)
        if thinking_val:
            set_thinking_level(thinking_val)
        # Build a one-line summary for the collapsed header
        model_label = next(
            (o["label"] for o in model_options() if o["value"] == (model_val or DEFAULT_MODEL)),
            "—",
        )
        thinking_label = next(
            (o["label"] for o in thinking_options() if o["value"] == (thinking_val or DEFAULT_THINKING)),
            "—",
        )
        # model_options labels look like "Sonnet 4.6  (balanced)" — strip the parens for the summary
        model_short = model_label.split("(")[0].strip()
        return f"· {model_short} · thinking: {thinking_label}"
