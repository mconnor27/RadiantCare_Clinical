"""
Header component with logo, title, and help icon
"""
from dash import html
import dash_bootstrap_components as dbc
import base64
from pathlib import Path


def get_base64_image(image_path):
    """Encode image to base64 for embedding in HTML"""
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()


def create_header():
    """
    Create the application header with logo, title, and help icon.

    Returns:
        Dash HTML component for header
    """
    logo_path = Path(__file__).parent.parent / "radiantcare.png"
    logo_base64 = get_base64_image(str(logo_path))

    return html.Div([
        # Logo and title on the left
        html.Div([
            html.Img(
                src=f"data:image/png;base64,{logo_base64}",
                style={
                    'height': '60px',
                    'marginRight': '12px',
                    'display': 'inline-block',
                    'verticalAlign': 'bottom'
                }
            ),
            html.H2(
                "Clinical Dashboard",
                style={
                    'display': 'inline-block',
                    'verticalAlign': 'bottom',
                    'color': 'rgb(124, 42, 131)',
                    'fontWeight': '900',
                    'fontFamily': '"Myriad Pro", Myriad, "Helvetica Neue", Arial, sans-serif',
                    'margin': '0',
                    'padding': '0',
                    'lineHeight': '1',
                    'marginBottom': '-4px'
                }
            )
        ], style={'display': 'inline-block'}),

        # Help icon on the right
        html.Div([
            html.I(
                className="fas fa-question-circle",
                id="help-icon",
                style={
                    'fontSize': '24px',
                    'color': 'rgb(124, 42, 131)',
                    'cursor': 'pointer',
                    'marginLeft': '15px'
                },
                title="Data Processing Notes"
            )
        ], style={'display': 'inline-block', 'float': 'right'}),

        # Modal for data processing notes
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Data Processing Notes")),
            dbc.ModalBody([
                html.H5("Tasks (Draw Volumes, Review Plan, Contour Review)", style={'marginTop': '0'}),
                html.Ul([
                    html.Li("Only appointments with a Primary Oncologist (FirstMD) are included"),
                    html.Li("Date/time parsing uses flexible dateutil parser"),
                    html.Li("Activity names are analyzed as-is from source data"),
                ]),

                html.Hr(),

                html.H5("Simulations"),
                html.Ul([
                    html.Li([
                        html.Strong("Location Mapping: "),
                        "CT_RC_LACEY → 'Lacey', CT_CENTRALIA → 'Centralia', 21iX_AB → 'Aberdeen'"
                    ]),
                    html.Li([
                        html.Strong("Filtered Out: "),
                        "Any simulation type containing 'Bite Block'"
                    ]),
                    html.Li([
                        html.Strong("Combined Types: "),
                        "'Treatment Device Fabrication' + 'initial simulation on PET/CT table' → 'PET/CT Sim'"
                    ]),
                    html.Li("Rows with unmapped locations are excluded from analysis"),
                    html.Li([
                        html.Strong("Duration Subtab: "),
                        "Shows mean appointment duration trends over time for all locations and each site individually. Data filtered to durations > 0 and ≤ 240 minutes. Choose monthly or quarterly aggregation."
                    ]),
                ]),

                html.Hr(),

                html.H5("Scheduling"),
                html.Ul([
                    html.Li("Data source: Appointment Status per Activity (Mike).csv"),
                    html.Li("CSV footer rows (filter metadata) automatically excluded during import"),
                    html.Li("Department names cleaned (asterisks removed): '*Lacey' → 'Lacey'"),
                    html.Li("Appointment date/time parsed from format: MM/DD/YYYY HH:MM:SS AM/PM"),
                    html.Li([
                        html.Strong("Filters: "),
                        "Department, Physician (ResourceName), Appointment Type (ActivityName), and Time of Day (8am-5pm hourly range)"
                    ]),
                    html.Li([
                        html.Strong("Department List (Reverse Alpha): "),
                        html.Span("Lacey", style={'backgroundColor': '#e3f2fd', 'border': '1px solid #2196f3', 'padding': '2px 6px', 'borderRadius': '3px', 'marginLeft': '5px', 'fontSize': '11px'}),
                        html.Span(", ", style={'marginRight': '3px'}),
                        html.Span("Centralia", style={'backgroundColor': '#f3e5f5', 'border': '1px solid #9c27b0', 'padding': '2px 6px', 'borderRadius': '3px', 'fontSize': '11px'}),
                        html.Span(", ", style={'marginRight': '3px'}),
                        html.Span("Aberdeen", style={'backgroundColor': '#e8f5e9', 'border': '1px solid #4caf50', 'padding': '2px 6px', 'borderRadius': '3px', 'fontSize': '11px'})
                    ]),
                    html.Li("Time range filter applies to appointment start time (hour component)"),
                    html.Li([
                        html.Strong("List View: "),
                        "Shows chronologically sorted appointments with pagination (10 per page)"
                    ]),
                    html.Li([
                        html.Strong("Calendar View: "),
                        "Time-scale weekly view (Monday-Friday, 8am-5pm) with color-coded department badges. Appointments positioned at their actual time slots with heights proportional to duration (60 pixels per hour). Navigate between weeks using the controls."
                    ]),
                    html.Li("All appointments shown include activity type, location, physician, and duration"),
                ]),

                html.Hr(),

                html.H5("Clinic Visits (Consults)"),
                html.Ul([
                    html.Li("Data source: Department Schedule No Grouping All (Mike)_exam.csv"),
                    html.Li("Cancelled appointments are excluded"),
                    html.Li([
                        html.Strong("Test patients excluded: "),
                        "PatientId contains 'astro' or 'test', OR PatientFullName starts with 'Zzz' or 'Test,' (filters out 12 test appointments)"
                    ]),
                    html.Li([
                        html.Strong("Invalid durations excluded: "),
                        "Appointments with duration ≤0 minutes are filtered out (removes 4 data errors)"
                    ]),
                    html.Li("Only activities containing 'Consult' in ActivityName are included"),
                    html.Li([
                        html.Strong("Date/Time: "),
                        "Uses ScheduledEndTime as the appointment time"
                    ]),
                    html.Li("Only consults with a Primary Oncologist (FirstMD extracted from ResourceName) are included"),
                    html.Li([
                        html.Strong("Appointment Type Classification: ")
                    ]),
                    html.Ul([
                        html.Li([
                            html.Strong(">60 minutes: "),
                            "Classified as ",
                            html.Span("Consult", style={'fontWeight': 'bold', 'color': '#2196f3'}),
                            " (new patient)"
                        ]),
                        html.Li([
                            html.Strong("≤60 minutes with ActivityName 'Consult', 'Consult - Special request', or 'Consult- ADD ON': ")
                        ]),
                        html.Ul([
                            html.Li([
                                "Default: ",
                                html.Span("Consult", style={'fontWeight': 'bold', 'color': '#2196f3'}),
                                " (new patient)"
                            ]),
                            html.Li([
                                "Exception: If ActivityNote contains 'follow-up', 'follow up', 'followup', 're-eval', 're eval', 'reeeval', or 'reeval' (case-insensitive, any spacing/hyphenation) → ",
                                html.Span("Follow-Up", style={'fontWeight': 'bold', 'color': '#4caf50'})
                            ])
                        ]),
                        html.Li([
                            html.Strong("≤60 minutes with ActivityName 'Virtual Consult/Follow Up': ")
                        ]),
                        html.Ul([
                            html.Li([
                                "If duration 0 < duration < 60 minutes (priority-based classification):"
                            ]),
                            html.Ul([
                                html.Li([
                                    "Priority 1: If note contains 'phone', 'telephone', 'follow-up', 'f/u', 're-eval', or 'reeval' → ",
                                    html.Span("Follow-Up", style={'fontWeight': 'bold', 'color': '#4caf50'})
                                ]),
                                html.Li([
                                    "Priority 2: If note contains 'review', 'discuss', or 'go over' → ",
                                    html.Span("Follow-Up", style={'fontWeight': 'bold', 'color': '#4caf50'})
                                ]),
                                html.Li([
                                    "Priority 3: If note contains 'working chart' or 'bookmarked' → ",
                                    html.Span("Consult", style={'fontWeight': 'bold', 'color': '#2196f3'}),
                                    " (new patient setup)"
                                ]),
                                html.Li([
                                    "Default: ",
                                    html.Span("Follow-Up", style={'fontWeight': 'bold', 'color': '#4caf50'}),
                                    " (conservative default)"
                                ])
                            ]),
                            html.Li([
                                "If duration =60 minutes:"
                            ]),
                            html.Ul([
                                html.Li([
                                    "If note contains follow-up/re-eval indicators → ",
                                    html.Span("Follow-Up", style={'fontWeight': 'bold', 'color': '#4caf50'})
                                ]),
                                html.Li([
                                    "If note mentions 'new' or no clear indicator → ",
                                    html.Span("Consult", style={'fontWeight': 'bold', 'color': '#2196f3'}),
                                    " (new patient)"
                                ])
                            ])
                        ])
                    ]),
                    html.Li([
                        html.Strong("Duration Histogram: "),
                        "Shows distribution of appointment durations using ActivityPlannedLength (in minutes). Mean and median lines are displayed for reference."
                    ])
                ]),

                html.Hr(),

                html.H5("General Notes"),
                html.Ul([
                    html.Li("All cumulative charts normalize leap years (Feb 29 combined with Feb 28)"),
                    html.Li("Year-to-date comparisons use day-of-year for alignment"),
                    html.Li("Historical statistics (mean, median, std dev, 95% CI) exclude the current period"),
                    html.Li("Projections use linear extrapolation based on current rate"),
                ]),
            ]),
            dbc.ModalFooter(
                dbc.Button("Close", id="close-help-modal", className="ms-auto", n_clicks=0)
            ),
        ], id="help-modal", is_open=False, size="lg"),

    ], style={'textAlign': 'center', 'position': 'relative'}, className='main-header')
