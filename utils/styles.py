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
    /* Department filter buttons (3D appearance with color accents) */
    .dept-filter-btn {
        flex: 0 0 auto;
        padding: 6px 12px;
        font-size: 13px;
        font-weight: 600;
        border: 2px solid #dee2e6;
        border-radius: 8px;
        background: linear-gradient(180deg, #ffffff 0%, #f8f9fa 100%);
        color: #495057;
        transition: all 0.2s ease;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1), 
                    0 1px 2px rgba(0, 0, 0, 0.08),
                    inset 0 -1px 2px rgba(0, 0, 0, 0.05);
        position: relative;
        cursor: pointer;
        margin: 0 3px;
    }
    .dept-filter-btn:first-child {
        margin-left: 0;
    }
    .dept-filter-btn:last-child {
        margin-right: 0;
    }
    .dept-filter-btn:hover {
        transform: translateY(-1px);
        box-shadow: 0 3px 5px rgba(0, 0, 0, 0.15), 
                    0 1px 2px rgba(0, 0, 0, 0.1),
                    inset 0 -1px 2px rgba(0, 0, 0, 0.05);
        color: #495057;
    }
    .dept-filter-btn:active {
        transform: translateY(1px);
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1), 
                    inset 0 1px 3px rgba(0, 0, 0, 0.1);
    }
    /* Lacey - Blue */
    .dept-filter-btn-lacey {
        border-color: #2196f3;
    }
    .dept-filter-btn-lacey:hover {
        border-color: #1976d2;
        background: linear-gradient(180deg, #e3f2fd 0%, #bbdefb 100%);
        color: #0d47a1;
    }
    .dept-filter-btn-lacey.dept-filter-btn-active {
        background: linear-gradient(180deg, #64b5f6 0%, #2196f3 100%);
        color: white;
        border-color: #1976d2;
        box-shadow: 0 2px 4px rgba(33, 150, 243, 0.3), 
                    0 1px 2px rgba(33, 150, 243, 0.2),
                    inset 0 -1px 2px rgba(0, 0, 0, 0.1),
                    inset 0 1px 1px rgba(255, 255, 255, 0.3);
    }
    .dept-filter-btn-lacey.dept-filter-btn-active:hover {
        background: linear-gradient(180deg, #90caf9 0%, #42a5f5 100%);
        box-shadow: 0 3px 5px rgba(33, 150, 243, 0.4), 
                    0 1px 2px rgba(33, 150, 243, 0.25),
                    inset 0 -1px 2px rgba(0, 0, 0, 0.1),
                    inset 0 1px 1px rgba(255, 255, 255, 0.3);
        color: white;
    }
    /* Centralia - Red */
    .dept-filter-btn-centralia {
        border-color: #f44336 !important;
    }
    .dept-filter-btn-centralia:hover {
        border-color: #d32f2f !important;
        background: linear-gradient(180deg, #ffebee 0%, #ffcdd2 100%) !important;
        color: #b71c1c !important;
    }
    .dept-filter-btn-centralia.dept-filter-btn-active {
        background: linear-gradient(180deg, #ef5350 0%, #f44336 100%) !important;
        color: white !important;
        border-color: #d32f2f !important;
        box-shadow: 0 2px 4px rgba(244, 67, 54, 0.3), 
                    0 1px 2px rgba(244, 67, 54, 0.2),
                    inset 0 -1px 2px rgba(0, 0, 0, 0.1),
                    inset 0 1px 1px rgba(255, 255, 255, 0.3) !important;
    }
    .dept-filter-btn-centralia.dept-filter-btn-active:hover {
        background: linear-gradient(180deg, #e57373 0%, #ef5350 100%) !important;
        box-shadow: 0 3px 5px rgba(244, 67, 54, 0.4), 
                    0 1px 2px rgba(244, 67, 54, 0.25),
                    inset 0 -1px 2px rgba(0, 0, 0, 0.1),
                    inset 0 1px 1px rgba(255, 255, 255, 0.3) !important;
        color: white !important;
    }
    /* Aberdeen - Green */
    .dept-filter-btn-aberdeen {
        border-color: #4caf50;
    }
    .dept-filter-btn-aberdeen:hover {
        border-color: #388e3c;
        background: linear-gradient(180deg, #e8f5e9 0%, #c8e6c9 100%);
        color: #1b5e20;
    }
    .dept-filter-btn-aberdeen.dept-filter-btn-active {
        background: linear-gradient(180deg, #81c784 0%, #4caf50 100%);
        color: white;
        border-color: #388e3c;
        box-shadow: 0 2px 4px rgba(76, 175, 80, 0.3), 
                    0 1px 2px rgba(76, 175, 80, 0.2),
                    inset 0 -1px 2px rgba(0, 0, 0, 0.1),
                    inset 0 1px 1px rgba(255, 255, 255, 0.3);
    }
    .dept-filter-btn-aberdeen.dept-filter-btn-active:hover {
        background: linear-gradient(180deg, #a5d6a7 0%, #66bb6a 100%);
        box-shadow: 0 3px 5px rgba(76, 175, 80, 0.4), 
                    0 1px 2px rgba(76, 175, 80, 0.25),
                    inset 0 -1px 2px rgba(0, 0, 0, 0.1),
                    inset 0 1px 1px rgba(255, 255, 255, 0.3);
        color: white;
    }
    /* Physician filter buttons (Purple) */
    .phys-filter-btn {
        flex: 0 0 auto !important;
        padding: 6px 12px !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        border: 2px solid #9c27b0 !important;
        border-radius: 8px !important;
        background: linear-gradient(180deg, #ffffff 0%, #f8f9fa 100%) !important;
        color: #495057 !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1), 
                    0 1px 2px rgba(0, 0, 0, 0.08),
                    inset 0 -1px 2px rgba(0, 0, 0, 0.05) !important;
        position: relative !important;
        cursor: pointer !important;
    }
    .phys-filter-btn:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 3px 5px rgba(0, 0, 0, 0.15), 
                    0 1px 2px rgba(0, 0, 0, 0.1),
                    inset 0 -1px 2px rgba(0, 0, 0, 0.05) !important;
        border-color: #7b1fa2 !important;
        background: linear-gradient(180deg, #f3e5f5 0%, #e1bee7 100%) !important;
        color: #4a148c !important;
    }
    .phys-filter-btn:active {
        transform: translateY(1px) !important;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1), 
                    inset 0 1px 3px rgba(0, 0, 0, 0.1) !important;
    }
    .phys-filter-btn.phys-filter-btn-active {
        background: linear-gradient(180deg, #ba68c8 0%, #9c27b0 100%) !important;
        color: white !important;
        border-color: #7b1fa2 !important;
        box-shadow: 0 2px 4px rgba(156, 39, 176, 0.3), 
                    0 1px 2px rgba(156, 39, 176, 0.2),
                    inset 0 -1px 2px rgba(0, 0, 0, 0.1),
                    inset 0 1px 1px rgba(255, 255, 255, 0.3) !important;
    }
    .phys-filter-btn.phys-filter-btn-active:hover {
        background: linear-gradient(180deg, #ce93d8 0%, #ab47bc 100%) !important;
        box-shadow: 0 3px 5px rgba(156, 39, 176, 0.4), 
                    0 1px 2px rgba(156, 39, 176, 0.25),
                    inset 0 -1px 2px rgba(0, 0, 0, 0.1),
                    inset 0 1px 1px rgba(255, 255, 255, 0.3) !important;
        color: white !important;
    }
    /* Appointment type filter buttons (Neutral Blue) */
    .appt-filter-btn {
        flex: 0 0 auto !important;
        padding: 6px 12px !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        border: 2px solid #2196f3 !important;
        border-radius: 8px !important;
        background: linear-gradient(180deg, #ffffff 0%, #f8f9fa 100%) !important;
        color: #495057 !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1), 
                    0 1px 2px rgba(0, 0, 0, 0.08),
                    inset 0 -1px 2px rgba(0, 0, 0, 0.05) !important;
        position: relative !important;
        cursor: pointer !important;
    }
    .appt-filter-btn:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 3px 5px rgba(0, 0, 0, 0.15), 
                    0 1px 2px rgba(0, 0, 0, 0.1),
                    inset 0 -1px 2px rgba(0, 0, 0, 0.05) !important;
        border-color: #1976d2 !important;
        background: linear-gradient(180deg, #e3f2fd 0%, #bbdefb 100%) !important;
        color: #0d47a1 !important;
    }
    .appt-filter-btn:active {
        transform: translateY(1px) !important;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1), 
                    inset 0 1px 3px rgba(0, 0, 0, 0.1) !important;
    }
    .appt-filter-btn.appt-filter-btn-active {
        background: linear-gradient(180deg, #64b5f6 0%, #2196f3 100%) !important;
        color: white !important;
        border-color: #1976d2 !important;
        box-shadow: 0 2px 4px rgba(33, 150, 243, 0.3), 
                    0 1px 2px rgba(33, 150, 243, 0.2),
                    inset 0 -1px 2px rgba(0, 0, 0, 0.1),
                    inset 0 1px 1px rgba(255, 255, 255, 0.3) !important;
    }
    .appt-filter-btn.appt-filter-btn-active:hover {
        background: linear-gradient(180deg, #90caf9 0%, #42a5f5 100%) !important;
        box-shadow: 0 3px 5px rgba(33, 150, 243, 0.4), 
                    0 1px 2px rgba(33, 150, 243, 0.25),
                    inset 0 -1px 2px rgba(0, 0, 0, 0.1),
                    inset 0 1px 1px rgba(255, 255, 255, 0.3) !important;
        color: white !important;
    }
    /* Scheduling sidebar fixed width */
    .scheduling-sidebar {
        width: 280px !important;
        min-width: 300px !important;
        max-width: 3000px !important;
        background-color: #F8F9FA;
        padding: 20px;
        padding-top: 0;
        border-right: 2px solid #E8E8E8;
        height: 100vh;
        overflow-y: auto;
    }
    /* Time range slider styling - clean and simple */
    .time-range-slider .rc-slider-rail {
        height: 8px !important;
    }
    .time-range-slider .rc-slider-track {
        height: 8px !important;
    }
    .time-range-slider .rc-slider-handle {
        width: 20px !important;
        height: 20px !important;
        margin-top: -6px !important;
        border-width: 3px !important;
    }
    /* Small fixed markers (dots) - move down 2px */
    .time-range-slider .rc-slider-dot {
        transform: translate(-50%, calc(-50% + 6px)) !important;
    }
    .time-range-slider .rc-slider-mark-text {
        font-size: 14px !important;
        font-weight: 500 !important;
        white-space: nowrap !important;
        width: auto !important;
        min-width: auto !important;
    }
"""
