"""
Header component with logo and title
"""
from dash import html
import base64
from pathlib import Path


def get_base64_image(image_path):
    """Encode image to base64 for embedding in HTML"""
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()


def create_header():
    """
    Create the application header with logo and title.

    Returns:
        Dash HTML component for header
    """
    logo_path = Path(__file__).parent.parent / "radiantcare.png"
    logo_base64 = get_base64_image(str(logo_path))

    return html.Div([
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
    ], style={'textAlign': 'center'}, className='main-header')
