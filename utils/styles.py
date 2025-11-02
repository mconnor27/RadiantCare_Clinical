"""
Custom CSS styles for the application
"""

CUSTOM_CSS = """
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        background-color: #FFFFFF;
    }
    .purple-checkbox input[type="checkbox"] {
        outline: none !important;
        box-shadow: none !important;
        border: 1px solid #ccc !important;
    }
    .purple-checkbox input[type="checkbox"]:checked {
        accent-color: rgb(124, 42, 131) !important;
        background-color: rgb(124, 42, 131) !important;
        border-color: rgb(124, 42, 131) !important;
    }
    .purple-checkbox input[type="checkbox"]:focus,
    .purple-checkbox input[type="checkbox"]:focus-visible {
        outline: none !important;
        box-shadow: none !important;
        border-color: rgb(124, 42, 131) !important;
    }
    .red-checkbox input[type="checkbox"] {
        outline: none !important;
        box-shadow: none !important;
        border: 1px solid #ccc !important;
    }
    .red-checkbox input[type="checkbox"]:checked {
        accent-color: #E74C3C !important;
        background-color: #E74C3C !important;
        border-color: #E74C3C !important;
    }
    .red-checkbox input[type="checkbox"]:focus,
    .red-checkbox input[type="checkbox"]:focus-visible {
        outline: none !important;
        box-shadow: none !important;
        border-color: #E74C3C !important;
    }
    .purple-apply-btn {
        background-color: rgb(124, 42, 131) !important;
        border-color: rgb(124, 42, 131) !important;
        color: white !important;
    }
    .purple-apply-btn:hover {
        background-color: rgb(100, 30, 110) !important;
        border-color: rgb(100, 30, 110) !important;
    }
    .red-apply-btn {
        background-color: #E74C3C !important;
        border-color: #E74C3C !important;
        color: white !important;
    }
    .red-apply-btn:hover {
        background-color: #C0392B !important;
        border-color: #C0392B !important;
    }
    .sidebar {
        background-color: #F8F9FA;
        padding: 20px;
        padding-top: 0;
        border-right: 2px solid #E8E8E8;
        height: 100vh;
        overflow-y: auto;
    }
    .main-header {
        border-bottom: 2px solid #E8E8E8;
        padding: 1rem 0;
        margin-bottom: 0;
    }
    .filter-section {
        margin-bottom: 1.5rem;
    }
    /* Make accordion items more compact */
    .accordion-button {
        padding: 0.5rem 1rem !important;
        font-size: 0.95rem !important;
    }
    .accordion-body {
        padding: 0.75rem 1rem !important;
    }
    /* Button panels with rounded edges and accented background */
    .button-panel {
        padding: 8px;
        border-radius: 8px;
        margin-bottom: 12px;
    }
    .purple-panel {
        background-color: rgba(124, 42, 131, 0.08);
        border: 1px solid rgba(124, 42, 131, 0.3);
    }
    .red-panel {
        background-color: rgba(231, 76, 60, 0.08);
        border: 1px solid rgba(231, 76, 60, 0.3);
    }
    /* Reduce spacing between buttons in panel */
    .button-panel .row {
        --bs-gutter-x: 0.5rem;
    }
    /* Make tooltip draggable and cursor pointer */
    .rc-slider-tooltip {
        cursor: grab !important;
        pointer-events: auto !important;
        user-select: none !important;
        -webkit-user-select: none !important;
        -moz-user-select: none !important;
        -ms-user-select: none !important;
    }
    .rc-slider-tooltip:active {
        cursor: grabbing !important;
    }
    /* Prevent text selection on slider */
    .rc-slider {
        user-select: none !important;
        -webkit-user-select: none !important;
        -moz-user-select: none !important;
        -ms-user-select: none !important;
    }
    /* Year range quick select buttons */
    .year-select-buttons {
        display: flex;
        gap: 6px;
        margin-bottom: 12px;
    }
    .year-select-buttons .btn {
        flex: 1;
        font-size: 0.85rem;
        padding: 6px 8px;
        border: 1px solid #dee2e6;
        background-color: white;
        color: #495057;
        transition: all 0.2s;
        white-space: nowrap;
        min-width: 0;
    }
    .year-select-buttons .btn:hover {
        background-color: #3498DB;
        border-color: #3498DB;
        color: white;
    }
    .year-select-buttons .btn:active {
        background-color: #2980B9 !important;
        border-color: #2980B9 !important;
    }
    .year-select-buttons .btn.active {
        background-color: #3498DB !important;
        border-color: #3498DB !important;
        color: white !important;
    }
"""
