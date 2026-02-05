"""
Scheduling main panel layout (appointments display)
"""
from dash import html, dcc
import dash_bootstrap_components as dbc
from datetime import datetime


# Appointment type mapping
APPOINTMENT_TYPE_MAP = {
    'HOLD CONSULT': 'Consult',
    'HOLD RE EVAL/2 FOLLOW UPS': 'Follow-up'
}


def get_appointment_type_display(activity_name):
    """
    Convert appointment activity name to display name.
    
    Args:
        activity_name: The ActivityName from the data
        
    Returns:
        Display name (Consult or Follow-up)
    """
    return APPOINTMENT_TYPE_MAP.get(activity_name, activity_name)


def create_main_panel_layout():
    """
    Create main panel layout for Scheduling task.

    Returns:
        Dash component for main panel
    """
    return html.Div([
        # List view container
        html.Div(id='sched-list-view-container', style={'display': 'none'}, children=[
            html.H5("Open Appointments", style={'marginTop': '20px', 'marginBottom': '15px'}),
            
            # Appointments list with max width and left aligned
            html.Div(id='sched-appointments-list', style={
                'maxWidth': '700px',
                'margin': '0'
            }),
            
            # Pagination controls - bottom
            html.Div([
                dbc.Button("◄", id="sched-prev-page", size="sm", color="secondary", style={
                    'padding': '4px 8px',
                    'minWidth': '32px'
                }),
                html.Span(id="sched-page-display", style={
                    'padding': '0 15px',
                    'fontWeight': '500',
                    'fontSize': '14px'
                }),
                dbc.Button("►", id="sched-next-page", size="sm", color="secondary", style={
                    'padding': '4px 8px',
                    'minWidth': '32px'
                }),
            ], style={
                'marginTop': '15px',
                'textAlign': 'center',
                'display': 'flex',
                'justifyContent': 'center',
                'alignItems': 'center',
                'gap': '5px'
            }),
        ]),

        # Calendar view container
        html.Div(id='sched-calendar-view-container', children=[
            # Week title with Today button (above calendar)
            html.Div([
                html.H5(id='sched-calendar-title', children="Week of", style={
                    'display': 'inline-block',
                    'marginRight': '10px',
                    'marginBottom': '0',
                    'marginTop': '0',
                    'verticalAlign': 'middle'
                }),
                dbc.Button("Today", id="sched-current-week-top", size="sm", color="primary", style={
                    'verticalAlign': 'middle'
                }),
            ], style={
                'textAlign': 'center', 
                'marginTop': '20px', 
                'marginBottom': '15px',
                'display': 'flex',
                'justifyContent': 'center',
                'alignItems': 'center',
                'gap': '10px'
            }),
            
            # Calendar grid with navigation arrows overlaid
            html.Div([
                html.Div(id='sched-calendar-grid'),
                
                # Left arrow - positioned in top-left corner box
                html.Div([
                    dbc.Button("◄ Prev", id="sched-prev-week-top", size="sm", color="secondary", style={
                        'fontSize': '13px',
                        'padding': '6px 12px'
                    }),
                ], style={
                    'position': 'absolute',
                    'left': '20px',
                    'top': '10px',
                    'zIndex': '10'
                }),
                
                # Right arrow - positioned in top-right corner box
                html.Div([
                    dbc.Button("Next ►", id="sched-next-week-top", size="sm", color="secondary", style={
                        'fontSize': '13px',
                        'padding': '6px 12px'
                    }),
                ], style={
                    'position': 'absolute',
                    'right': '15px',
                    'top': '10px',
                    'zIndex': '10'
                }),
            ], style={'position': 'relative'})
        ]),
        
        # Store for selected departments
        dcc.Store(id='sched-selected-depts-store', data=['Lacey', 'Centralia', 'Aberdeen']),
        # Store for selected physicians
        dcc.Store(id='sched-selected-phys-store', data=[0, 1, 2, 3]),
        # Store for selected appointment types
        dcc.Store(id='sched-selected-appt-store', data=['HOLD CONSULT', 'HOLD RE EVAL/2 FOLLOW UPS']),
        # Store for current page (list view)
        dcc.Store(id='sched-current-page', data=1),
        # Store for week offset (calendar view)
        dcc.Store(id='sched-week-offset', data=0),
        # Week display (hidden, used by calendar view)
        html.Div(id='sched-week-display', style={'display': 'none'})
    ])


def create_appointment_card(appointment, department_colors):
    """
    Create a card for a single appointment.

    Args:
        appointment: Series with appointment data
        department_colors: Dict mapping department names to color schemes

    Returns:
        Dash component for appointment card
    """
    appt_datetime = appointment['AppointmentDateTime']
    date_str = appt_datetime.strftime('%A, %B %d, %Y')
    time_str = appt_datetime.strftime('%I:%M %p')
    end_time = appointment['EndTime'].strftime('%I:%M %p')
    appt_type_display = get_appointment_type_display(appointment['ActivityName'])
    
    # Get department color
    dept_name = appointment['DepartmentName']
    colors = department_colors.get(dept_name, {'bg': '#e3f2fd', 'border': '#2196f3'})
    
    # Convert hex color to RGB for badge background and card background
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    rgb_border = hex_to_rgb(colors['border'])
    rgb_bg = hex_to_rgb(colors['bg'])
    
    # Create more subtle background color with reduced opacity
    subtle_bg = f'rgba({rgb_bg[0]}, {rgb_bg[1]}, {rgb_bg[2]}, 0.3)'
    
    # Create badge styles
    dept_badge_style = {
        'display': 'inline-block',
        'fontSize': '11px',
        'fontWeight': '600',
        'color': colors['border'],
        'backgroundColor': f'rgba({rgb_border[0]}, {rgb_border[1]}, {rgb_border[2]}, 0.15)',
        'padding': '4px 10px',
        'borderRadius': '6px',
        'border': f'1px solid {colors["border"]}',
        'whiteSpace': 'nowrap'
    }
    
    # Physician badge style (purple theme)
    phys_badge_style = {
        'display': 'inline-block',
        'fontSize': '11px',
        'fontWeight': '600',
        'color': '#7b1fa2',
        'backgroundColor': 'rgba(156, 39, 176, 0.15)',
        'padding': '4px 10px',
        'borderRadius': '6px',
        'border': '1px solid #9c27b0',
        'whiteSpace': 'nowrap'
    }

    return dbc.Card([
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.I(className="fas fa-calendar-day", style={'marginRight': '8px', 'color': '#6c757d'}),
                        html.Strong(date_str, style={'fontSize': '15px'})
                    ], style={'marginBottom': '8px'}),
                    html.Div([
                        html.I(className="fas fa-clock", style={'marginRight': '8px', 'color': '#6c757d'}),
                        html.Span(f"{time_str} - {end_time} ({int(appointment['ActivityPlannedLength'])} min)", 
                                 style={'fontSize': '14px', 'color': '#495057'})
                    ], style={'marginBottom': '8px'}),
                    html.Div([
                        html.I(className="fas fa-notes-medical", style={'marginRight': '8px', 'color': '#6c757d'}),
                        html.Span(appt_type_display, style={'fontSize': '13px', 'color': '#6c757d'})
                    ]),
                ], width=6),
                dbc.Col([
                    html.Div([
                        html.Span(appointment['ResourceName'], style=phys_badge_style)
                    ], style={'marginBottom': '8px', 'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-end'}),
                    html.Div([
                        html.Span(dept_name, style=dept_badge_style)
                    ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-end'}),
                ], width=6),
            ]),
        ])
    ], style={
        'marginBottom': '12px', 
        'boxShadow': '0 2px 6px rgba(0,0,0,0.08)',
        'border': f'1px solid {colors["border"]}',
        'borderLeft': f'4px solid {colors["border"]}',
        'borderRadius': '8px',
        'backgroundColor': subtle_bg,
        'transition': 'all 0.2s ease'
    })


def create_list_view(appointments_df, department_colors):
    """
    Create list view of appointments.

    Args:
        appointments_df: DataFrame with appointments for current page
        department_colors: Dict mapping department names to color schemes

    Returns:
        List of appointment card components
    """
    if appointments_df.empty:
        return [html.Div("No appointments found for the selected filters.",
                        style={'textAlign': 'center', 'padding': '40px', 'color': '#6c757d'})]

    return [create_appointment_card(row, department_colors) for _, row in appointments_df.iterrows()]


def create_calendar_view(weekly_df, week_start, week_end, department_colors):
    """
    Create weekly calendar view (Monday - Friday) with time-scale positioning.

    Args:
        weekly_df: DataFrame with appointments for the week
        week_start: datetime for start of week (Monday)
        week_end: datetime for end of week (Friday)
        department_colors: Dict mapping department names to color schemes

    Returns:
        Calendar grid component
    """
    from datetime import date as date_class, timedelta
    
    weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    dates = [(week_start + timedelta(days=i)) for i in range(5)]

    # Time scale parameters (8am - 5pm = 10 hours including 5pm)
    start_hour = 8
    end_hour = 17
    total_hours = end_hour - start_hour + 1  # Include the end hour (5 PM)
    pixels_per_hour = 60  # Height in pixels for each hour
    total_height = total_hours * pixels_per_hour  # 600px for 10 hours

    # Group appointments by day
    appointments_by_day = {day: [] for day in weekdays}

    if not weekly_df.empty:
        for _, appt in weekly_df.iterrows():
            day_name = appt['DayOfWeek']
            if day_name in weekdays:
                appointments_by_day[day_name].append(appt)

    # Create time labels (left side)
    time_labels = []
    for hour in range(start_hour, end_hour + 1):
        suffix = 'AM' if hour < 12 else 'PM'
        display_hour = hour if hour <= 12 else hour - 12
        if display_hour == 0:
            display_hour = 12
        time_labels.append(
            html.Div(f"{display_hour} {suffix}", style={
                'height': f'{pixels_per_hour}px',
                'lineHeight': f'{pixels_per_hour}px',
                'fontSize': '11px',
                'color': '#6c757d',
                'borderTop': '1px solid #dee2e6',
                'paddingRight': '8px',
                'textAlign': 'right'
            })
        )

    # Create calendar grid
    calendar_cols = [
        # Time labels column
        dbc.Col([
            html.Div([
                html.Div(style={'height': '50px'}),  # Header spacer
                html.Div(time_labels, style={'position': 'relative'})
            ])
        ], width=1, style={'paddingRight': '0'})
    ]

    for i, (day, date) in enumerate(zip(weekdays, dates)):
        day_appointments = appointments_by_day[day]
        date_str = date.strftime('%b %d')
        
        # Check if this date is today
        today = date_class.today()
        is_today = date.date() == today

        # Create appointment items positioned by time
        appt_items = []
        if day_appointments:
            for appt in day_appointments:
                appt_hour = appt['AppointmentDateTime'].hour
                appt_minute = appt['AppointmentDateTime'].minute

                # Skip appointments outside our time range
                if appt_hour < start_hour or appt_hour > end_hour:
                    continue

                # Calculate position from top (in pixels)
                hours_from_start = (appt_hour - start_hour) + (appt_minute / 60)
                top_position = hours_from_start * pixels_per_hour

                # Calculate height based on duration
                duration_minutes = appt['ActivityPlannedLength']
                badge_height = (duration_minutes / 60) * pixels_per_hour

                time_str = appt['AppointmentDateTime'].strftime('%I:%M %p')

                # Get department color
                dept_name = appt['DepartmentName']
                colors = department_colors.get(dept_name, {'bg': '#e3f2fd', 'border': '#2196f3'})
                
                appt_type_display = get_appointment_type_display(appt['ActivityName'])
                
                # Darken the border color while retaining its hue (mix 75% black with 25% original color)
                def darken_color(hex_color, black_ratio=0.75):
                    """Darken a hex color by mixing with black"""
                    hex_color = hex_color.lstrip('#')
                    r = int(hex_color[0:2], 16)
                    g = int(hex_color[2:4], 16)
                    b = int(hex_color[4:6], 16)
                    # Mix with black
                    r = int(r * (1 - black_ratio))
                    g = int(g * (1 - black_ratio))
                    b = int(b * (1 - black_ratio))
                    return f'#{r:02x}{g:02x}{b:02x}'
                
                darkened_color = darken_color(colors['border'], black_ratio=0.75)
                
                # Badge styling
                badge_style = {
                    'fontSize': '8px',
                    'fontWeight': 'bold',
                    'color': darkened_color,  # Darkened version of original color
                    'backgroundColor': f'rgba({int(colors["border"][1:3], 16)}, {int(colors["border"][3:5], 16)}, {int(colors["border"][5:7], 16)}, 0.25)',
                    'padding': '2px 6px',
                    'borderRadius': '3px',
                    'textAlign': 'center',
                    'whiteSpace': 'nowrap',
                    'width': 'fit-content'
                }
                
                # Create badge element
                badge_element = html.Div(appt['DepartmentName'], style=badge_style)
                
                # Check if this is a 30-minute appointment
                is_30_min = duration_minutes == 30
                
                if is_30_min:
                    # 30-minute appointments: single line with time, physician, location
                    appt_items.append(
                        html.Div([
                            html.Div(time_str, style={'fontWeight': 'bold', 'fontSize': '10px', 'marginRight': '8px', 'whiteSpace': 'nowrap'}),
                            html.Div(appt['ResourceName'], style={'fontSize': '11px', 'marginRight': '8px', 'overflow': 'hidden', 'textOverflow': 'ellipsis', 'whiteSpace': 'nowrap', 'flex': '1', 'minWidth': '0'}),
                            badge_element
                        ], style={
                            'position': 'absolute',
                            'top': f'{top_position}px',
                            'left': '2px',
                            'right': '2px',
                            'height': f'{badge_height}px',
                            'backgroundColor': colors['bg'],
                            'border': f"2px solid {colors['border']}",
                            'borderRadius': '4px',
                            'padding': '4px',
                            'fontSize': '10px',
                            'boxSizing': 'border-box',
                            'overflow': 'hidden',
                            'zIndex': '1',
                            'display': 'flex',
                            'flexDirection': 'row',
                            'alignItems': 'center',
                            'gap': '4px'
                        })
                    )
                else:
                    # Longer appointments: vertical layout with time, name, type, and badge in top right
                    content_section = html.Div([
                        html.Div(time_str, style={'fontWeight': 'bold', 'fontSize': '10px', 'marginBottom': '2px'}),
                        html.Div(appt['ResourceName'], style={'fontSize': '11px', 'marginBottom': '1px', 'overflow': 'hidden', 'textOverflow': 'ellipsis', 'whiteSpace': 'nowrap'}),
                        html.Div(appt_type_display, style={'fontSize': '10px', 'color': '#6c757d', 'marginBottom': '1px', 'overflow': 'hidden', 'textOverflow': 'ellipsis', 'whiteSpace': 'nowrap'}),
                    ], style={'flex': '1', 'display': 'flex', 'flexDirection': 'column', 'minWidth': '0'})

                    appt_items.append(
                        html.Div([
                            content_section,
                            badge_element
                        ], style={
                            'position': 'absolute',
                            'top': f'{top_position}px',
                            'left': '2px',
                            'right': '2px',
                            'height': f'{badge_height}px',
                            'backgroundColor': colors['bg'],
                            'border': f"2px solid {colors['border']}",
                            'borderRadius': '4px',
                            'padding': '4px',
                            'fontSize': '10px',
                            'boxSizing': 'border-box',
                            'overflow': 'hidden',
                            'zIndex': '1',
                            'display': 'flex',
                            'flexDirection': 'row',
                            'justifyContent': 'space-between',
                            'alignItems': 'flex-start'
                        })
                    )

        # Create the day column with time grid
        time_grid = []
        for hour in range(start_hour, end_hour + 1):
            time_grid.append(
                html.Div(style={
                    'height': f'{pixels_per_hour}px',
                    'borderTop': '1px solid #dee2e6',
                    'borderLeft': '1px solid #dee2e6',
                    'borderRight': '1px solid #dee2e6',
                    'backgroundColor': '#fdfdfd'  # Very faint shading for time cells
                })
            )

        # Style for today's column
        header_style = {
            'textAlign': 'center', 
            'padding': '8px', 
            'height': '50px',
            'backgroundColor': '#e9ecef'  # Darker background for headers
        }
        card_style = {'border': '1px solid #dee2e6'}
        
        if is_today:
            header_style.update({
                'backgroundColor': 'rgba(33, 150, 243, 0.25)',  # Darker blue highlight for today
                'borderBottom': '2px solid #2196f3'
            })
            card_style.update({
                'border': '2px solid #2196f3',
                'boxShadow': '0 2px 8px rgba(33, 150, 243, 0.2)'
            })
        
        calendar_cols.append(
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Div(day, style={'fontWeight': 'bold', 'fontSize': '12px', 'color': '#212529'}),
                        html.Div(date_str, style={'fontSize': '11px', 'color': '#495057'})
                    ], style=header_style),
                    html.Div([
                        html.Div(time_grid),
                        html.Div(appt_items, style={'position': 'relative', 'top': f'-{total_height}px', 'pointerEvents': 'none'})
                    ], style={
                        'position': 'relative',
                        'height': f'{total_height}px',
                        'overflowY': 'visible'
                    })
                ], style=card_style)
            ], width=12, lg=2, style={'marginBottom': '10px', 'paddingLeft': '2px', 'paddingRight': '2px'})
        )

    # Add right-side time labels column (after Friday)
    calendar_cols.append(
        dbc.Col([
            html.Div([
                html.Div(style={'height': '50px'}),  # Header spacer
                html.Div(time_labels, style={'position': 'relative'})
            ])
        ], width=1, style={'paddingLeft': '0'})
    )
    
    return html.Div(
        dbc.Row(calendar_cols),
        style={'width': '1200px', 'margin': '0 auto'}
    )


def register_callbacks(app, task):
    """Register callbacks for scheduling panel"""
    from dash import Input, Output, State, callback_context, clientside_callback

    # Department filter button callbacks (for calendar view)
    @app.callback(
        [Output('sched-selected-depts-store', 'data'),
         Output('sched-dept-btn-lacey', 'className'),
         Output('sched-dept-btn-centralia', 'className'),
         Output('sched-dept-btn-aberdeen', 'className')],
        [Input('sched-dept-btn-lacey', 'n_clicks'),
         Input('sched-dept-btn-centralia', 'n_clicks'),
         Input('sched-dept-btn-aberdeen', 'n_clicks')],
        [State('sched-selected-depts-store', 'data')],
        prevent_initial_call=True
    )
    def update_dept_buttons(lacey_clicks, centralia_clicks, aberdeen_clicks, current_depts):
        """Update department button selection (min 1, max 3)"""
        ctx = callback_context
        if not ctx.triggered:
            return current_depts, 'dept-filter-btn dept-filter-btn-active', 'dept-filter-btn dept-filter-btn-active', 'dept-filter-btn dept-filter-btn-active'
        
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        
        # Determine which department was clicked
        dept_map = {
            'sched-dept-btn-lacey': 'Lacey',
            'sched-dept-btn-centralia': 'Centralia',
            'sched-dept-btn-aberdeen': 'Aberdeen'
        }
        clicked_dept = dept_map.get(button_id)
        
        if clicked_dept:
            if clicked_dept in current_depts:
                # Deselect only if more than 1 department is selected (minimum 1)
                if len(current_depts) > 1:
                    current_depts = [d for d in current_depts if d != clicked_dept]
            else:
                # Select only if less than 3 departments are selected (maximum 3)
                if len(current_depts) < 3:
                    current_depts = current_depts + [clicked_dept]
        
        # Update button classes based on selection
        lacey_class = 'dept-filter-btn dept-filter-btn-active dept-filter-btn-lacey' if 'Lacey' in current_depts else 'dept-filter-btn dept-filter-btn-lacey'
        centralia_class = 'dept-filter-btn dept-filter-btn-active dept-filter-btn-centralia' if 'Centralia' in current_depts else 'dept-filter-btn dept-filter-btn-centralia'
        aberdeen_class = 'dept-filter-btn dept-filter-btn-active dept-filter-btn-aberdeen' if 'Aberdeen' in current_depts else 'dept-filter-btn dept-filter-btn-aberdeen'
        
        return current_depts, lacey_class, centralia_class, aberdeen_class

    # Physician filter button callbacks
    @app.callback(
        [Output('sched-selected-phys-store', 'data'),
         Output('sched-phys-btn-0', 'className'),
         Output('sched-phys-btn-1', 'className'),
         Output('sched-phys-btn-2', 'className'),
         Output('sched-phys-btn-3', 'className')],
        [Input('sched-phys-btn-0', 'n_clicks'),
         Input('sched-phys-btn-1', 'n_clicks'),
         Input('sched-phys-btn-2', 'n_clicks'),
         Input('sched-phys-btn-3', 'n_clicks')],
        [State('sched-selected-phys-store', 'data')],
        prevent_initial_call=True
    )
    def update_phys_buttons(btn0_clicks, btn1_clicks, btn2_clicks, btn3_clicks, current_phys):
        """Update physician button selection (min 1)"""
        ctx = callback_context
        if not ctx.triggered:
            return current_phys, 'phys-filter-btn phys-filter-btn-active', 'phys-filter-btn phys-filter-btn-active', 'phys-filter-btn phys-filter-btn-active', 'phys-filter-btn phys-filter-btn-active'
        
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        
        # Determine which physician was clicked
        phys_map = {
            'sched-phys-btn-0': 0,
            'sched-phys-btn-1': 1,
            'sched-phys-btn-2': 2,
            'sched-phys-btn-3': 3
        }
        clicked_phys = phys_map.get(button_id)
        
        if clicked_phys is not None:
            if clicked_phys in current_phys:
                # Deselect only if more than 1 physician is selected (minimum 1)
                if len(current_phys) > 1:
                    current_phys = [p for p in current_phys if p != clicked_phys]
            else:
                # Select the physician
                current_phys = current_phys + [clicked_phys]
        
        # Update button classes based on selection
        btn0_class = 'phys-filter-btn phys-filter-btn-active' if 0 in current_phys else 'phys-filter-btn'
        btn1_class = 'phys-filter-btn phys-filter-btn-active' if 1 in current_phys else 'phys-filter-btn'
        btn2_class = 'phys-filter-btn phys-filter-btn-active' if 2 in current_phys else 'phys-filter-btn'
        btn3_class = 'phys-filter-btn phys-filter-btn-active' if 3 in current_phys else 'phys-filter-btn'
        
        return current_phys, btn0_class, btn1_class, btn2_class, btn3_class

    # Appointment type filter button callbacks
    @app.callback(
        [Output('sched-selected-appt-store', 'data'),
         Output('sched-appt-btn-consult', 'className'),
         Output('sched-appt-btn-followup', 'className')],
        [Input('sched-appt-btn-consult', 'n_clicks'),
         Input('sched-appt-btn-followup', 'n_clicks')],
        [State('sched-selected-appt-store', 'data')],
        prevent_initial_call=True
    )
    def update_appt_buttons(consult_clicks, followup_clicks, current_appts):
        """Update appointment type button selection (min 1)"""
        ctx = callback_context
        if not ctx.triggered:
            return current_appts, 'appt-filter-btn appt-filter-btn-active', 'appt-filter-btn appt-filter-btn-active'
        
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        
        # Map button IDs to appointment types
        appt_map = {
            'sched-appt-btn-consult': 'HOLD CONSULT',
            'sched-appt-btn-followup': 'HOLD RE EVAL/2 FOLLOW UPS'
        }
        clicked_appt = appt_map.get(button_id)
        
        if clicked_appt is not None:
            if clicked_appt in current_appts:
                # Deselect only if more than 1 type is selected (minimum 1)
                if len(current_appts) > 1:
                    current_appts = [a for a in current_appts if a != clicked_appt]
            else:
                # Select the appointment type
                current_appts = current_appts + [clicked_appt]
        
        # Update button classes based on selection
        consult_class = 'appt-filter-btn appt-filter-btn-active' if 'HOLD CONSULT' in current_appts else 'appt-filter-btn'
        followup_class = 'appt-filter-btn appt-filter-btn-active' if 'HOLD RE EVAL/2 FOLLOW UPS' in current_appts else 'appt-filter-btn'
        
        return current_appts, consult_class, followup_class

    # Time range display callback - clientside for real-time updates during drag
    clientside_callback(
        """
        function(time_range) {
            if (!time_range || time_range.length !== 2) {
                return "8:00 AM - 5:00 PM";
            }
            const start_hour = time_range[0];
            const end_hour = time_range[1];
            const start_suffix = start_hour < 12 ? "AM" : "PM";
            const end_suffix = end_hour < 12 ? "AM" : "PM";
            const start_display = start_hour <= 12 ? start_hour : start_hour - 12;
            const end_display = end_hour <= 12 ? end_hour : end_hour - 12;
            return start_display + ":00 " + start_suffix + " - " + end_display + ":00 " + end_suffix;
        }
        """,
        Output('sched-time-range-display', 'children'),
        Input('sched-time-range-slider', 'value')
    )

    # View mode toggle - show/hide pagination or week controls
    # Pagination callbacks
    @app.callback(
        Output('sched-current-page', 'data'),
        [Input('sched-prev-page', 'n_clicks'),
         Input('sched-next-page', 'n_clicks'),
         Input('sched-selected-depts-store', 'data'),
         Input('sched-selected-phys-store', 'data'),
         Input('sched-selected-appt-store', 'data'),
         Input('sched-time-range-slider', 'value')],
        [State('sched-current-page', 'data')],
        prevent_initial_call=True
    )
    def update_page(prev_clicks, next_clicks, depts, physicians, appt_types, time_range, current_page):
        """Update current page based on navigation buttons"""
        ctx = callback_context
        if not ctx.triggered:
            return 1

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        # Reset to page 1 if filters changed
        if button_id in ['sched-selected-depts-store', 'sched-selected-phys-store', 'sched-selected-appt-store', 'sched-time-range-slider']:
            return 1

        # Handle pagination
        if button_id == 'sched-prev-page':
            return max(1, current_page - 1)
        elif button_id == 'sched-next-page':
            return current_page + 1

        return current_page

    # Week navigation callbacks
    @app.callback(
        Output('sched-week-offset', 'data'),
        [Input('sched-prev-week-top', 'n_clicks'),
         Input('sched-next-week-top', 'n_clicks'),
         Input('sched-current-week-top', 'n_clicks')],
        [State('sched-week-offset', 'data'),
         State('sched-prev-week-top', 'disabled'),
         State('sched-current-week-top', 'disabled')],
        prevent_initial_call=True
    )
    def update_week_offset(prev_top_clicks, next_top_clicks, current_top_clicks, current_offset, prev_disabled, today_disabled):
        """Update week offset based on navigation buttons"""
        from dash.exceptions import PreventUpdate
        
        ctx = callback_context
        if not ctx.triggered:
            return 0

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'sched-prev-week-top':
            # Prevent navigation if button is disabled
            if prev_disabled:
                raise PreventUpdate
            return current_offset - 1
        elif button_id == 'sched-next-week-top':
            return current_offset + 1
        elif button_id == 'sched-current-week-top':
            # Prevent navigation if button is disabled
            if today_disabled:
                raise PreventUpdate
            return 0

        return current_offset

    # Disable Prev button when today is in the displayed week
    @app.callback(
        Output('sched-prev-week-top', 'disabled'),
        Input('sched-week-offset', 'data')
    )
    def update_prev_button_state(week_offset):
        """Disable Prev button when today is in the displayed week"""
        from datetime import datetime, timedelta, date as date_class
        
        # Calculate the displayed week start (Monday)
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday())
        week_start = week_start + timedelta(weeks=week_offset)
        week_end = week_start + timedelta(days=4)  # M-F only
        
        # Check if today's date is within the displayed week
        today_date = date_class.today()
        week_start_date = week_start.date()
        week_end_date = week_end.date()
        
        # Disable if today is in the displayed week
        return week_start_date <= today_date <= week_end_date

    # Disable Today button when today is already in the displayed week
    @app.callback(
        Output('sched-current-week-top', 'disabled'),
        Input('sched-week-offset', 'data')
    )
    def update_today_button_state(week_offset):
        """Disable Today button when today is already in the displayed week"""
        from datetime import datetime, timedelta, date as date_class
        
        # Calculate the displayed week start (Monday)
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday())
        week_start = week_start + timedelta(weeks=week_offset)
        week_end = week_start + timedelta(days=4)  # M-F only
        
        # Check if today's date is within the displayed week
        today_date = date_class.today()
        week_start_date = week_start.date()
        week_end_date = week_end.date()
        
        # Disable if today is already in the displayed week
        return week_start_date <= today_date <= week_end_date

    # Main update callback - updates all content
    @app.callback(
        [Output('sched-appointments-list', 'children'),
         Output('sched-page-display', 'children'),
         Output('sched-list-view-container', 'style'),
         Output('sched-calendar-view-container', 'style'),
         Output('sched-calendar-grid', 'children'),
         Output('sched-calendar-title', 'children'),
         Output('sched-week-display', 'children')],
        [Input('sched-selected-depts-store', 'data'),
         Input('sched-selected-phys-store', 'data'),
         Input('sched-selected-appt-store', 'data'),
         Input('sched-time-range-slider', 'value'),
         Input('sched-view-mode', 'value'),
         Input('sched-current-page', 'data'),
         Input('sched-week-offset', 'data')]
    )
    def update_content(selected_depts, selected_phys_indices, selected_appt_types, time_range, view_mode, current_page, week_offset):
        """Update all content based on filters and view mode"""
        # Convert physician indices to names
        selected_physicians = [task.physicians[i] for i in selected_phys_indices if i < len(task.physicians)]
        
        # Filter data
        filtered_df = task.filter_data(selected_depts, selected_physicians, selected_appt_types, time_range)

        # Prepare content based on view mode
        if view_mode == 'list':
            # List view
            paginated_df, total_pages = task.get_paginated_appointments(filtered_df, current_page, page_size=10)
            appointments_list = create_list_view(paginated_df, task.department_colors)
            page_display = f"Page {current_page} of {total_pages}" if total_pages > 0 else "No data"

            return (
                appointments_list, page_display,
                {'display': 'block'}, {'display': 'none'},
                [], "", ""
            )
        else:
            # Calendar view
            weekly_df, week_start, week_end = task.get_weekly_calendar_data(filtered_df, week_offset)
            calendar_grid = create_calendar_view(weekly_df, week_start, week_end, task.department_colors)
            calendar_title = f"Week of {week_start.strftime('%B %d, %Y')}"
            week_display = f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}"

            return (
                [], "",
                {'display': 'none'}, {'display': 'block'},
                calendar_grid, calendar_title, week_display
            )
