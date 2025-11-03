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
        border-bottom: none;
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
        flex: 0 1 auto;
        font-size: 0.85rem;
        padding: 6px 12px;
        border: 1px solid #dee2e6;
        background-color: white;
        color: #495057;
        transition: all 0.2s;
        white-space: nowrap;
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
    /* Left align sort icons with spacing */
    .dash-table-container th .column-actions {
        margin-right: 8px !important;
    }
    /* Tab styling */
    .main-tabs {
        margin-bottom: 0;
        border-bottom: none;
    }
    .main-tabs .nav-tabs {
        border-bottom: none;
        margin-bottom: 0;
        background-color: transparent;
        padding-left: 0;
        position: relative;
        top: 2px;
    }
    .main-tabs .nav-link {
        color: #495057;
        border: 1px solid transparent;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        background-color: #F8F9FA;
        padding: 10px 20px;
        margin-right: 2px;
        margin-bottom: -2px;
        font-weight: 500;
        transition: all 0.2s;
        position: relative;
    }
    .main-tabs .nav-link:hover {
        color: rgb(124, 42, 131);
        background-color: #E9ECEF;
        border-color: #dee2e6 #dee2e6 transparent;
    }
    .main-tabs .nav-link.active {
        color: rgb(124, 42, 131);
        background-color: #FFFFFF;
        border-color: #dee2e6 #dee2e6 transparent;
        font-weight: 600;
        z-index: 99;
        position: relative;
    }
    .main-tabs .nav-link.active::after {
        content: '';
        position: absolute;
        bottom: -2px;
        left: 0;
        right: 0;
        height: 2px;
        background-color: #FFFFFF;
        z-index: 10;
    }
    .main-tabs .nav-link.disabled {
        color: #adb5bd;
        cursor: not-allowed;
        opacity: 0.8;
        background-color: #F8F9FA;
        border: 1px solid #dee2e6;
    }
    .main-tabs .tab-content {
        background-color: #FFFFFF;
        padding: 0;
        border-left: 1px solid #dee2e6;
        border-right: 1px solid #dee2e6;
        border-bottom: 1px solid #dee2e6;
    }
    /* Subtabs styling */
    .subtabs {
        background-color: #FAFBFC;
        border-bottom: 1px solid #E8E8E8;
        padding: 8px 0;
        margin-bottom: 0;
    }
    .subtabs .nav-pills {
        gap: 8px;
    }
    .subtabs .nav-link {
        color: #495057;
        background-color: #FFFFFF;
        border: 1px solid #dee2e6;
        border-radius: 6px;
        padding: 6px 16px;
        font-size: 0.9rem;
        transition: all 0.2s;
    }
    .subtabs .nav-link:hover {
        color: rgb(124, 42, 131);
        border-color: rgb(124, 42, 131);
        background-color: rgba(124, 42, 131, 0.05);
    }
    .subtabs .nav-link.active {
        color: white;
        background-color: rgb(124, 42, 131);
        border-color: rgb(124, 42, 131);
    }
    .tab-content-area {
        padding: 20px;
    }
    /* Max width for charts and stat badges */
    #main-chart {
        max-width: 1000px;
    }
    .tab-content-area > div > .row {
        max-width: 1000px;
    }
"""
