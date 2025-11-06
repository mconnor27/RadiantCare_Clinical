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
