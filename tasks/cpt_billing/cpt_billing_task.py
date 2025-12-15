"""
CPT Billing task implementation
"""
import pandas as pd
from tasks.base_task import BaseTask


class CPTBillingTask(BaseTask):
    """Task for 2026 CPT billing code analysis"""

    def __init__(self, df):
        """
        Initialize CPT Billing task.

        Args:
            df: Pandas DataFrame with CPT billing data
        """
        super().__init__(df)

        # Process the CPT data
        self.df = self._process_cpt_data(df)

        # Define custom order for 2026 codes
        self.codes_2026_order = ['77402', '77407', '77412', '77372', '77373']

        # Get unique values for filters
        self.departments = sorted(self.df['Department'].dropna().unique())
        self.machines = sorted(self.df['Machine'].dropna().unique())
        self.insurers = sorted(self.df['PrimaryInsurer'].dropna().unique())
        self.insurer_categories = sorted(self.df['InsurerCategory'].dropna().unique())

        # Order 2026 codes according to custom order
        unique_2026_codes = self.df['ID2026Code'].dropna().unique()
        self.codes_2026 = [code for code in self.codes_2026_order if code in unique_2026_codes]
        # Add any codes not in the predefined order at the end (sorted)
        other_codes = sorted([code for code in unique_2026_codes if code not in self.codes_2026_order])
        self.codes_2026.extend(other_codes)

        self.radiation_types = sorted(self.df['RadiationType'].dropna().unique())

        # Get unique individual techniques (expand comma-separated values)
        all_techniques = []
        for tech_str in self.df['Technique'].dropna():
            techniques = [t.strip() for t in str(tech_str).split(',')]
            all_techniques.extend(techniques)
        self.techniques = sorted(set(all_techniques))

        # Get unique actual billing codes
        all_actual_codes = []
        for codes_str in self.df['BilledCodes'].dropna():
            codes = [c.strip() for c in str(codes_str).split(',')]
            all_actual_codes.extend(codes)
        self.actual_codes = sorted(set(all_actual_codes))

        # Get date range for time frame filter
        self.min_date = self.df['TreatmentDate'].min()
        self.max_date = self.df['TreatmentDate'].max()

    def _process_cpt_data(self, df):
        """
        Process CPT billing data.

        Args:
            df: Original DataFrame

        Returns:
            DataFrame with processed CPT data
        """
        df = df.copy()

        # Clean up Department - remove leading asterisks
        df['Department'] = df['Department'].str.replace('*', '', regex=False)

        # Parse TreatmentDate column
        df['TreatmentDate'] = pd.to_datetime(df['TreatmentDate'], format='%m/%d/%Y')

        # Extract year for filtering
        df['Year'] = df['TreatmentDate'].dt.year

        # Fill empty PrimaryInsurer with "Unknown"
        df['PrimaryInsurer'] = df['PrimaryInsurer'].fillna('Unknown')

        # Add insurer category grouping
        df['InsurerCategory'] = df['PrimaryInsurer'].apply(self._categorize_insurer)

        # Add technique classification based on billed codes
        df['Technique'] = df['BilledCodes'].apply(self._categorize_technique)

        return df

    def _categorize_insurer(self, insurer):
        """
        Categorize insurer into Medicare, Medicaid, or Private.

        Args:
            insurer: Insurer name string

        Returns:
            Category string: 'Medicare', 'Medicaid', 'Private', or 'Unknown'
        """
        if pd.isna(insurer) or insurer == 'Unknown' or insurer == '':
            return 'Unknown'

        insurer_upper = str(insurer).upper()

        # Medicare patterns (including Medicare Advantage plans)
        medicare_keywords = [
            'MEDICARE',
            'MEDADVANTAGE',
            'MED ADVANTAGE',
            'MEDICARE ADVANTAGE'
        ]

        # Medicaid patterns (including managed care plans)
        medicaid_keywords = [
            'MEDICAID',
            'CHPW MEDICAID',
            'APPLE HEALTH',
            'MOLINA MEDICAID'
        ]

        # Check for Medicare
        for keyword in medicare_keywords:
            if keyword in insurer_upper:
                return 'Medicare'

        # Check for Medicaid
        for keyword in medicaid_keywords:
            if keyword in insurer_upper:
                return 'Medicaid'

        # Everything else is Private
        return 'Private'

    def _categorize_technique(self, billed_codes_str):
        """
        Categorize treatment technique based on billed CPT codes.
        Returns comma-separated list of all applicable techniques.

        Args:
            billed_codes_str: Comma-separated string of CPT codes

        Returns:
            Comma-separated string of techniques: e.g., 'IMRT, IGRT' or 'Conventional'
        """
        if pd.isna(billed_codes_str) or billed_codes_str == '':
            return 'Unknown'

        # Parse codes
        codes = [c.strip() for c in str(billed_codes_str).split(',')]
        codes_set = set(codes)

        # Define technique code sets
        conventional_codes = {'77402', 'G6003', 'G6004', 'G6005', 'G6006', '77407', 'G6007', 'G6008', 'G6009', 'G6010', '77412', 'G6011', 'G6012', 'G6013', 'G6014'}
        srs_codes = {'77372'}
        sbrt_codes = {'77373'}
        imrt_codes = {'77385', '77386', 'G6015', 'G6016'}
        igrt_codes = {'77014', '77387', 'G6002'}

        # Collect all applicable techniques in priority order
        techniques = []

        # Check in order of specificity (most specific first)
        if codes_set & sbrt_codes:
            techniques.append('SBRT')
        if codes_set & srs_codes:
            techniques.append('SRS')
        if codes_set & imrt_codes:
            techniques.append('IMRT')
        if codes_set & igrt_codes:
            techniques.append('IGRT')
        if codes_set & conventional_codes:
            techniques.append('Conventional')

        # Return comma-separated techniques or 'Other' if none matched
        if techniques:
            return ', '.join(techniques)
        else:
            return 'Other'

    def filter_data(self, selected_departments, selected_machines, selected_insurer_categories, selected_insurers,
                    start_date=None, end_date=None, selected_techniques=None, selected_codes_2026=None,
                    selected_radiation_types=None, selected_actual_codes=None):
        """
        Filter dataframe based on user selections.

        Args:
            selected_departments: List of selected departments
            selected_machines: List of selected machines
            selected_insurer_categories: List of selected insurer categories (Medicare, Medicaid, Private)
            selected_insurers: List of selected specific insurers
            start_date: Start date for filtering (inclusive)
            end_date: End date for filtering (inclusive)
            selected_techniques: List of selected techniques
            selected_codes_2026: List of selected 2026 codes
            selected_radiation_types: List of selected radiation types
            selected_actual_codes: List of selected actual billing codes

        Returns:
            Filtered DataFrame
        """
        if selected_departments is None:
            selected_departments = self.departments
        if selected_machines is None:
            selected_machines = self.machines
        if selected_insurer_categories is None:
            selected_insurer_categories = self.insurer_categories
        if selected_insurers is None:
            selected_insurers = self.insurers
        if selected_techniques is None:
            selected_techniques = self.techniques
        if selected_codes_2026 is None:
            selected_codes_2026 = self.codes_2026
        if selected_radiation_types is None:
            selected_radiation_types = self.radiation_types

        filtered_df = self.df[
            (self.df['Department'].isin(selected_departments)) &
            (self.df['Machine'].isin(selected_machines)) &
            (self.df['InsurerCategory'].isin(selected_insurer_categories)) &
            (self.df['PrimaryInsurer'].isin(selected_insurers)) &
            (self.df['ID2026Code'].isin(selected_codes_2026)) &
            (self.df['RadiationType'].isin(selected_radiation_types))
        ].copy()

        # Apply date range filter if provided
        print(f"DEBUG filter_data: start_date={start_date}, end_date={end_date}, rows before date filter={len(filtered_df)}")
        if start_date is not None:
            filtered_df = filtered_df[filtered_df['TreatmentDate'] >= start_date]
        if end_date is not None:
            filtered_df = filtered_df[filtered_df['TreatmentDate'] <= end_date]
        print(f"DEBUG filter_data: rows after date filter={len(filtered_df)}")

        # Filter by techniques if specified (check if any selected technique is in the comma-separated list)
        if selected_techniques is not None and selected_techniques != self.techniques:
            mask = filtered_df['Technique'].apply(
                lambda x: any(tech.strip() in selected_techniques for tech in str(x).split(',')) if pd.notna(x) else False
            )
            filtered_df = filtered_df[mask]

        # Filter by actual billing codes if specified
        if selected_actual_codes is not None and selected_actual_codes != self.actual_codes:
            # Filter rows that contain at least one of the selected actual codes
            mask = filtered_df['BilledCodes'].apply(
                lambda x: any(code.strip() in selected_actual_codes for code in str(x).split(',')) if pd.notna(x) else False
            )
            filtered_df = filtered_df[mask]

        return filtered_df

    def calculate_code_summary(self, filtered_df):
        """
        Calculate summary of billing codes.

        Args:
            filtered_df: Filtered DataFrame

        Returns:
            DataFrame with code counts and percentages
        """
        if filtered_df.empty:
            return pd.DataFrame(columns=['Code', 'Count', 'Percentage', 'Type'])

        summary_data = []

        # Count 2026 codes
        code_2026_counts = filtered_df['ID2026Code'].value_counts()
        total_2026 = code_2026_counts.sum()

        for code, count in code_2026_counts.items():
            if pd.notna(code):
                percentage = (count / total_2026 * 100) if total_2026 > 0 else 0
                summary_data.append({
                    'Code': code,
                    'Count': count,
                    'Percentage': f'{percentage:.1f}%',
                    'Type': '2026 Billing Code'
                })

        # Count billed codes (need to parse the comma-separated list)
        # Extract all billed codes from the BilledCodes column
        all_billed_codes = []
        for codes_str in filtered_df['BilledCodes'].dropna():
            codes = [c.strip() for c in str(codes_str).split(',')]
            all_billed_codes.extend(codes)

        billed_code_counts = pd.Series(all_billed_codes).value_counts()
        total_billed = len(all_billed_codes)

        for code, count in billed_code_counts.items():
            if code:  # Skip empty strings
                percentage = (count / total_billed * 100) if total_billed > 0 else 0
                summary_data.append({
                    'Code': code,
                    'Count': count,
                    'Percentage': f'{percentage:.1f}%',
                    'Type': 'Actual Billing Code'
                })

        summary_df = pd.DataFrame(summary_data)

        # Sort by Type then Code
        if not summary_df.empty:
            summary_df = summary_df.sort_values(['Type', 'Code'])

        return summary_df

    def calculate_sankey_data(self, filtered_df):
        """
        Calculate Sankey diagram data showing flow from actual billing codes to 2026 codes.

        Args:
            filtered_df: Filtered DataFrame

        Returns:
            Tuple of (source_list, target_list, value_list, labels_list)
        """
        if filtered_df.empty:
            return [], [], [], []

        # Build mappings from actual codes to 2026 codes
        code_flows = {}  # {(actual_code, code_2026): count}

        for _, row in filtered_df.iterrows():
            code_2026 = row['ID2026Code']
            billed_codes_str = row['BilledCodes']

            # Skip if no 2026 code
            if pd.isna(code_2026) or code_2026 == '':
                continue

            # Parse billed codes
            if pd.notna(billed_codes_str):
                billed_codes = [c.strip() for c in str(billed_codes_str).split(',')]
                for billed_code in billed_codes:
                    if billed_code:  # Skip empty strings
                        key = (billed_code, code_2026)
                        code_flows[key] = code_flows.get(key, 0) + 1

        if not code_flows:
            return [], [], [], []

        # Create unique labels for all codes
        all_actual_codes = sorted(set([k[0] for k in code_flows.keys()]))
        all_2026_codes = sorted(set([k[1] for k in code_flows.keys()]))

        # Calculate counts for 2026 codes (right side) - use filtered_df to match table logic
        code_2026_counts = filtered_df['ID2026Code'].value_counts().to_dict()

        # Calculate total for percentages - use count of treatments, not flow instances
        total_2026 = len(filtered_df[filtered_df['ID2026Code'].notna()])

        # Create labels with counts/percentages for 2026 codes
        labels_actual = all_actual_codes
        labels_2026 = []
        for code in all_2026_codes:
            count = code_2026_counts.get(code, 0)
            percentage = (count / total_2026 * 100) if total_2026 > 0 else 0
            labels_2026.append(f"{code} ({count:,}, {percentage:.1f}%)")

        # Create label list and index mapping
        labels = labels_actual + labels_2026
        label_to_index = {}
        for idx, code in enumerate(all_actual_codes):
            label_to_index[code] = idx
        for idx, code in enumerate(all_2026_codes):
            label_to_index[code] = len(all_actual_codes) + idx

        # Build source, target, value lists for Sankey
        source = []
        target = []
        value = []

        for (actual_code, code_2026), count in code_flows.items():
            source.append(label_to_index[actual_code])
            target.append(label_to_index[code_2026])
            value.append(count)

        return source, target, value, labels

    def calculate_parallel_categories_data(self, filtered_df, selected_dimensions=None):
        """
        Calculate parallel categories data with dynamically selected dimensions ending in 2026 Code.

        Args:
            filtered_df: Filtered DataFrame
            selected_dimensions: List of dimension keys to include (in order)
                Options: 'actual_codes', 'department', 'machine', 'insurer_category'

        Returns:
            Tuple of (dimensions_list, counts_list, df_valid) for parallel categories
        """
        if filtered_df.empty:
            return [], [], None

        # Filter to only rows with valid 2026 codes
        df_valid = filtered_df[filtered_df['ID2026Code'].notna()].copy()

        if df_valid.empty:
            return [], [], None

        # Default dimensions if none selected or empty list
        if not selected_dimensions or len(selected_dimensions) == 0:
            selected_dimensions = ['machine', 'insurer_category']

        print(f"DEBUG: Selected dimensions: {selected_dimensions}")
        print(f"DEBUG: Initial df_valid rows: {len(df_valid)}")

        def _normalize_category_series(s):
            """
            Normalize a pandas Series for Plotly categorical axes.

            This prevents visually-identical duplicates like 77407 (int) vs "77407" (str)
            and hidden whitespace variants that can lead to repeated labels in Parcats.
            """
            import unicodedata

            # Start with pandas string dtype to avoid mixed int/float/str categories
            s = s.astype("string").fillna("Unknown")

            # Replace "non-breaking" and other space-like chars with normal spaces,
            # and drop zero-width / directionality markers that can make two strings
            # *look* identical in the browser but remain distinct categories.
            s = s.str.replace(r"[\u00A0\u2007\u202F]", " ", regex=True)          # NBSP family -> space
            s = s.str.replace(r"[\u200B\u200C\u200D\uFEFF]", "", regex=True)    # zero-width/BOM -> remove
            s = s.str.replace(r"[\u200E\u200F\u202A-\u202E\u2066-\u2069]", "", regex=True)  # bidi marks -> remove

            # Normalize Unicode to collapse lookalikes (e.g., full-width digits)
            s = s.map(lambda x: unicodedata.normalize("NFKC", x) if isinstance(x, str) else x)

            # Collapse internal whitespace and trim
            s = s.str.replace(r"\s+", " ", regex=True).str.strip()

            # Avoid empty categories
            return s.replace("", "Unknown")

        # Calculate 2026 code stats from ORIGINAL data (before any expansion)
        # This ensures 2026 totals match the table
        # Use string keys to match later lookups
        original_2026_counts = df_valid['ID2026Code'].value_counts()
        original_2026_total = original_2026_counts.sum()
        code_2026_stats_original = {}
        for code, count in original_2026_counts.items():
            percentage = (count / original_2026_total * 100) if original_2026_total > 0 else 0
            code_2026_stats_original[str(code)] = {'count': int(count), 'percentage': percentage}
        print(f"DEBUG: 2026 stats keys: {list(code_2026_stats_original.keys())}")
        
        # For actual codes, we need to expand the dataframe FIRST
        # This must happen before building dimensions
        if 'actual_codes' in selected_dimensions:
            print("DEBUG: Expanding dataframe for actual codes...")
            import time
            start = time.time()

            df_valid = df_valid.copy()
            # Split the BilledCodes into lists
            df_valid['ActualCode'] = df_valid['BilledCodes'].str.split(',').apply(
                lambda x: [c.strip() for c in x] if isinstance(x, list) else ['Unknown']
            )

            # Explode the ActualCode column (no weighting)
            df_valid = df_valid.explode('ActualCode', ignore_index=True)

            # Normalize to avoid duplicate-looking categories (e.g., "77407" vs 77407)
            df_valid['ActualCode'] = _normalize_category_series(df_valid['ActualCode'])

            # Remove empty codes
            df_valid = df_valid[df_valid['ActualCode'].str.len() > 0]

            print(f"DEBUG: Expanded to {len(df_valid)} rows with ActualCode in {time.time()-start:.2f}s")
            print(f"DEBUG: Sample ActualCode values: {list(df_valid['ActualCode'].unique()[:10])}")
        else:
            print("DEBUG: Not expanding - actual_codes not in selected dimensions")

        # Expand technique if it's in selected dimensions (split comma-separated techniques)
        if 'technique' in selected_dimensions:
            print("DEBUG: Expanding dataframe for techniques...")
            import time
            start = time.time()
            
            df_valid = df_valid.copy()
            df_valid['TechniqueExpanded'] = df_valid['Technique'].str.split(',').apply(
                lambda x: [t.strip() for t in x] if isinstance(x, list) else ['Unknown']
            )
            
            # Explode the TechniqueExpanded column (no weighting)
            df_valid = df_valid.explode('TechniqueExpanded', ignore_index=True)
            
            # Normalize
            df_valid['TechniqueExpanded'] = _normalize_category_series(df_valid['TechniqueExpanded'])
            
            # Remove empty techniques
            df_valid = df_valid[df_valid['TechniqueExpanded'].str.len() > 0]
            
            print(f"DEBUG: Expanded to {len(df_valid)} rows with TechniqueExpanded in {time.time()-start:.2f}s")
            print(f"DEBUG: Sample Technique values: {list(df_valid['TechniqueExpanded'].unique()[:10])}")

        # Build dimensions based on selection
        # Use expanded columns when available
        technique_col = 'TechniqueExpanded' if 'technique' in selected_dimensions else 'Technique'
        dimension_map = {
            'actual_codes': ('Actual Billed Codes', 'ActualCode'),
            '2026_codes': ('2026 Code', 'ID2026Code'),
            'department': ('Department', 'Department'),
            'machine': ('Machine', 'Machine'),
            'insurer_category': ('Insurer Category', 'InsurerCategory'),
            'technique': ('Technique', technique_col),
            'radiation_type': ('Radiation Type', 'RadiationType')
        }

        dimensions = []
        groupby_cols = []

        for dim_key in selected_dimensions:
            if dim_key in dimension_map:
                label, col = dimension_map[dim_key]
                # Normalize then convert to category dtype for better performance
                _orig = df_valid[col].astype("string")
                _norm = _normalize_category_series(_orig)
                if _orig.nunique(dropna=False) != _norm.nunique(dropna=False):
                    # Print a small sample so we can see what was collapsing (in terminal logs)
                    examples = (
                        pd.DataFrame({"orig": _orig, "norm": _norm})
                        .drop_duplicates()
                        .query("orig != norm")
                        .head(5)
                        .to_dict("records")
                    )
                    print(
                        f"DEBUG: Normalization collapsed categories for {col}: "
                        f"{_orig.nunique(dropna=False)} -> {_norm.nunique(dropna=False)}; examples={examples}"
                    )
                df_valid[col] = _norm.astype('category')
                if col == "Machine":
                    try:
                        cats = df_valid[col].cat.categories.tolist()
                        print(f"DEBUG: Machine categories (repr): {[repr(c) for c in cats]}")
                    except Exception as e:
                        print(f"DEBUG: Could not read Machine categories: {e}")
                dimensions.append(dict(
                    label=label,
                    values=df_valid[col],
                    categoryorder='array'  # Force Plotly to use our categoryarray
                ))
                groupby_cols.append(col)

        # Count occurrences (each expanded row counts as 1)
        import time
        start = time.time()
        counts = df_valid.groupby(groupby_cols, observed=True).size().reset_index(name='count')
        print(f"DEBUG: Groupby completed in {time.time()-start:.2f}s")

        # Use the original 2026 code stats calculated BEFORE expansion
        # This ensures labels match the table totals
        return dimensions, counts, df_valid, code_2026_stats_original

    def get_sidebar_layout(self, state=None):
        """Implemented in cpt_billing_sidebar.py"""
        from tasks.cpt_billing.cpt_billing_sidebar import create_sidebar_layout
        return create_sidebar_layout(self, state=state)

    def get_main_panel_layout(self):
        """Implemented in cpt_billing_panel.py"""
        from tasks.cpt_billing.cpt_billing_panel import create_main_panel_layout
        return create_main_panel_layout()

    def register_callbacks(self, app):
        """Implemented in cpt_billing_panel.py"""
        from tasks.cpt_billing.cpt_billing_panel import register_callbacks
        register_callbacks(app, self)
