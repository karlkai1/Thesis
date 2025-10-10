This script selects a subset of traffic detectors for a simulation using a stratified sampling approach with spatial constraints, and allows manual additions.
Main Process:
1. Loads Detector Data

Reads detector information from filtered_detector_data.csv
Loads detector-to-edge mapping (tries fixed version first, falls back to simplified)
Focuses on October 9, 2024 traffic data

2. Calculates Daily Traffic Flow

Sums up FlowRate_1 for each detector on October 9
Categorizes detectors into traffic bins: <3k, 3k-5k, 5k-7k, 7k-10k, 10k-15k, 15k-20k, >20k vehicles/day

3. Quality Filtering

Removes detectors with zero flow
Filters out detectors more than 25m from their assigned lane (poor positioning)

4. Stratified Selection (Automatic)

Calculates proportional targets: if 20% of detectors are in "3k-5k" category, select ~20% from that category
Enforces minimum 300m spacing between selected detectors
Sorts candidates by distance from center for better spatial distribution
Attempts to select target number (default 40) while respecting spacing constraint
May select fewer than target if spacing constraint can't be satisfied

5. Manual Addition (Interactive)

Shows visualization with ALL detector IDs and daily flow counts
Displays top 100 available detectors by traffic flow
User can specify spacing policy:

Enforce spacing (reject violations)
Warn but allow (add with warnings)
Ignore spacing completely
Use custom spacing value


User enters detector IDs (comma-separated) to add manually
Script validates and adds requested detectors

6. Saves Results

filtered_detector_data_{n}_stratified_manual.csv - Traffic data for selected detectors (October 9 only)
detector_to_edge_mapping_{n}_stratified_manual.csv - Mapping with lane information and selection method (auto/manual)
final_detector_selection.png - Visualization showing auto-selected (circles) and manually-added (squares) detectors

Key Features:

Stratified: Maintains proportional representation across traffic volume categories
Spatial constraint: Ensures detectors aren't too close together (default 300m)
Quality control: Only uses detectors close to their lanes (<25m)
Interactive: Allows manual override and additions
Visual feedback: Shows all available detectors with IDs and counts for informed manual selection

Purpose:
Creates a representative subset of detectors for simulation validation - balancing traffic volume diversity, spatial coverage, and data quality.
