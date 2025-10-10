#!/usr/bin/env python3
"""
Stratified spatial detector selection - Enhanced with flexible manual selection
Allows overriding spacing constraints and batch manual addition
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.spatial import distance_matrix
import xml.etree.ElementTree as ET
from xml.dom import minidom
import sys
import json


def select_with_min_spacing(candidates, already_selected, min_spacing=300):
    """
    Select detectors from candidates ensuring minimum spacing from already selected ones.
    Returns list of selected SiteIDs
    """
    selected = []

    for _, candidate in candidates.iterrows():
        # Check distance to all already selected detectors
        too_close = False

        for _, existing in already_selected.iterrows():
            dist = np.sqrt((candidate['sumo_x'] - existing['sumo_x']) ** 2 +
                           (candidate['sumo_y'] - existing['sumo_y']) ** 2)
            if dist < min_spacing:
                too_close = True
                break

        if not too_close:
            selected.append(candidate['SiteID'])
            # Add to already_selected for next iteration
            already_selected = pd.concat([already_selected, candidate.to_frame().T], ignore_index=True)

    return selected, already_selected


def select_stratified_detectors_with_spacing(target_count=30, min_spacing=300, max_lane_distance=25):
    """
    Main selection function with enforced minimum spacing

    Args:
        target_count: Number of detectors to select
        min_spacing: Minimum spacing between selected detectors (meters)
        max_lane_distance: Maximum distance from detector to lane for quality filtering (meters)
    """

    print("=" * 80)
    print("STRATIFIED SPATIAL DETECTOR SELECTION WITH MINIMUM SPACING")
    print("=" * 80)

    # Load data
    df = pd.read_csv('filtered_detector_data.csv')

    # Load mapping
    mapping = pd.read_csv('detector_to_edge_mapping.csv')
    print("Using simplified mapping")
    # Rename columns for compatibility
    if 'distance' in mapping.columns:
        mapping['edge_distance'] = mapping['distance']
    if 'lane_0' in mapping.columns:
        mapping['lane_id'] = mapping['lane_0']
        # Estimate lane_distance as same as edge_distance if not available
        mapping['lane_distance'] = mapping.get('lane_distance', mapping['edge_distance'])

    # Convert flow columns
    for col in ['FlowRate_1', 'FlowRate_2', 'FlowRate_3']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # Get Oct 9 data
    df['Timestamp_parsed'] = pd.to_datetime(df['Timestamp'])
    df['date'] = df['Timestamp_parsed'].dt.date
    oct9_date = pd.to_datetime('2024-10-09').date()
    df_oct9 = df[df['date'] == oct9_date].copy()

    # Calculate daily totals
    daily_totals = df_oct9.groupby('SiteID')['FlowRate_1'].sum().reset_index()
    daily_totals.columns = ['SiteID', 'daily_flow']

    # Merge with mapping
    mapping['SiteID'] = mapping['detector_id'].astype(float).astype(int)
    detector_info = mapping.merge(daily_totals, on='SiteID', how='inner')

    # Quality filtering
    initial_count = len(detector_info)
    detector_info = detector_info[detector_info['daily_flow'] > 0].reset_index(drop=True)

    # Filter by lane distance if available
    if 'lane_distance' in detector_info.columns:
        before_lane_filter = len(detector_info)
        detector_info = detector_info[detector_info['lane_distance'] <= max_lane_distance].reset_index(drop=True)
        excluded_by_distance = before_lane_filter - len(detector_info)
        if excluded_by_distance > 0:
            print(f"Excluded {excluded_by_distance} detectors more than {max_lane_distance}m from their lane")

    total_detectors = len(detector_info)
    print(f"\nTotal valid detectors: {total_detectors}")
    print(f"Target: {target_count} detectors")
    print(f"Minimum spacing: {min_spacing} meters")
    print(f"Maximum lane distance: {max_lane_distance} meters")

    # Define traffic categories
    traffic_bins = [0, 3000, 5000, 7000, 10000, 15000, 20000, float('inf')]
    traffic_labels = ['<3k', '3k-5k', '5k-7k', '7k-10k', '10k-15k', '15k-20k', '>20k']

    detector_info['traffic_category'] = pd.cut(detector_info['daily_flow'],
                                               bins=traffic_bins,
                                               labels=traffic_labels)

    # Calculate proportional targets
    category_targets = {}
    print("\n" + "=" * 80)
    print("STRATIFIED SAMPLING PLAN")
    print("=" * 80)

    for label in traffic_labels:
        cat_count = (detector_info['traffic_category'] == label).sum()
        if cat_count > 0:
            proportion = cat_count / total_detectors
            target = max(1, int(np.round(target_count * proportion)))  # At least 1 if category exists
            category_targets[label] = min(target, cat_count)  # Don't exceed available
        else:
            category_targets[label] = 0

        if cat_count > 0:
            print(f"{label:<10}: {cat_count:3} available, target {category_targets[label]:2}")

    # Selection with spacing constraint
    print("\n" + "=" * 80)
    print("SELECTING WITH SPACING CONSTRAINT")
    print("=" * 80)

    selected_detectors = pd.DataFrame()  # Will store all selected detectors
    total_selected = 0

    for label in traffic_labels:
        if category_targets.get(label, 0) == 0:
            continue

        cat_detectors = detector_info[detector_info['traffic_category'] == label].copy()
        target = category_targets[label]

        print(f"\n{label}: Target {target} from {len(cat_detectors)} available")

        # Sort by distance from center for better spatial distribution
        center_x = cat_detectors['sumo_x'].mean()
        center_y = cat_detectors['sumo_y'].mean()
        cat_detectors['dist_from_center'] = np.sqrt(
            (cat_detectors['sumo_x'] - center_x) ** 2 +
            (cat_detectors['sumo_y'] - center_y) ** 2
        )

        # For multi-lane roads, prefer diverse lane coverage
        if 'lane_index' in cat_detectors.columns:
            # Add small penalty for lane 0 to encourage diversity
            cat_detectors['selection_score'] = cat_detectors['dist_from_center']
            # Slightly prefer non-lane-0 detectors if we have many lane 0s
            lane_0_ratio = (cat_detectors['lane_index'] == 0).mean()
            if lane_0_ratio > 0.5:  # If more than 50% are lane 0
                cat_detectors.loc[cat_detectors['lane_index'] != 0, 'selection_score'] *= 0.95
            cat_sorted = cat_detectors.sort_values('selection_score')
        else:
            cat_sorted = cat_detectors.sort_values('dist_from_center')

        # Try different sorting strategies to maximize selection
        selected_ids = []

        for _, candidate in cat_sorted.iterrows():
            if len(selected_ids) >= target:
                break

            # Check spacing to all already selected
            too_close = False
            if len(selected_detectors) > 0:
                for _, existing in selected_detectors.iterrows():
                    dist = np.sqrt((candidate['sumo_x'] - existing['sumo_x']) ** 2 +
                                   (candidate['sumo_y'] - existing['sumo_y']) ** 2)
                    if dist < min_spacing:
                        too_close = True
                        break

            if not too_close:
                selected_ids.append(candidate['SiteID'])
                selected_detectors = pd.concat([selected_detectors, candidate.to_frame().T],
                                               ignore_index=True)

        actual_selected = len(selected_ids)
        total_selected += actual_selected

        if actual_selected < target:
            print(f"  WARNING: Only selected {actual_selected}/{target} due to {min_spacing}m spacing")
        else:
            print(f"  Selected {actual_selected} detectors successfully")

    print(f"\n" + "=" * 80)
    print(f"TOTAL SELECTED: {total_selected} detectors")

    # Calculate spacing statistics
    if len(selected_detectors) > 1:
        coords = selected_detectors[['sumo_x', 'sumo_y']].values
        dist_matrix = distance_matrix(coords, coords)
        np.fill_diagonal(dist_matrix, np.inf)
        min_distances = dist_matrix.min(axis=1)

        print(f"\nSpacing Statistics:")
        print(f"  Minimum: {min_distances.min():.0f}m")
        print(f"  Average: {min_distances.mean():.0f}m")
        print(f"  Maximum: {min_distances.max():.0f}m")

        violations = (min_distances < min_spacing).sum()
        if violations > 0:
            print(f"  WARNING: {violations} pairs violate {min_spacing}m constraint")

    return selected_detectors, detector_info


def plot_all_detectors_with_labels(selected, all_detectors, title, highlight_manually_added=None, show_all_labels=True):
    """
    Create a plot showing ALL detectors with their IDs and daily vehicle counts.
    """
    fig, ax = plt.subplots(figsize=(20, 14))

    # Get unselected detectors
    unselected = all_detectors[~all_detectors['SiteID'].isin(selected['SiteID'])]

    # Plot unselected detectors with semi-transparent gray
    ax.scatter(unselected['sumo_x'], unselected['sumo_y'],
               c='lightgray', s=50, alpha=0.4, label=f'Available ({len(unselected)})',
               edgecolors='gray', linewidth=0.5)

    # Add labels for ALL unselected detectors
    if show_all_labels:
        for _, detector in unselected.iterrows():
            label = f"{int(detector['SiteID'])}\n{int(detector['daily_flow']):,}"
            ax.annotate(label,
                        (detector['sumo_x'], detector['sumo_y']),
                        xytext=(0, 0), textcoords='offset points',
                        fontsize=6, ha='center', va='center',
                        alpha=0.6,
                        bbox=dict(boxstyle="round,pad=0.2", facecolor='lightgray',
                                  alpha=0.3, edgecolor='none'))

    # Color scheme for traffic categories
    colors = {'<3k': 'green', '3k-5k': 'yellow', '5k-7k': 'orange',
              '7k-10k': 'red', '10k-15k': 'darkred', '15k-20k': 'purple', '>20k': 'black'}

    # Plot selected detectors with different colors based on traffic category
    for cat in selected['traffic_category'].unique():
        if pd.notna(cat):
            cat_data = selected[selected['traffic_category'] == cat]

            # Check if any detectors in this category are manually added
            if highlight_manually_added:
                auto_selected = cat_data[~cat_data['SiteID'].isin(highlight_manually_added)]
                manual_selected = cat_data[cat_data['SiteID'].isin(highlight_manually_added)]

                # Plot auto-selected with normal markers
                if len(auto_selected) > 0:
                    ax.scatter(auto_selected['sumo_x'], auto_selected['sumo_y'],
                               c=colors.get(cat, 'blue'), s=200,
                               label=f'{cat} ({len(auto_selected)} auto)',
                               edgecolors='black', linewidth=2, marker='o', zorder=5)

                # Plot manually-selected with square markers
                if len(manual_selected) > 0:
                    ax.scatter(manual_selected['sumo_x'], manual_selected['sumo_y'],
                               c=colors.get(cat, 'blue'), s=250,
                               label=f'{cat} ({len(manual_selected)} manual)',
                               edgecolors='black', linewidth=3, marker='s', zorder=5)
            else:
                ax.scatter(cat_data['sumo_x'], cat_data['sumo_y'],
                           c=colors.get(cat, 'blue'), s=200,
                           label=f'{cat} ({len(cat_data)})',
                           edgecolors='black', linewidth=2, zorder=5)

    # Add labels for selected detectors (more prominent)
    for _, detector in selected.iterrows():
        label = f"{int(detector['SiteID'])}\n{int(detector['daily_flow']):,}"

        # Determine if this is a manually added detector
        if highlight_manually_added and detector['SiteID'] in highlight_manually_added:
            # Manual detectors get bold text with yellow background
            bbox_props = dict(boxstyle="round,pad=0.3", facecolor='yellow',
                              alpha=0.9, edgecolor='black', linewidth=2)
            fontweight = 'bold'
            fontsize = 8
        else:
            # Auto-selected detectors get normal text
            bbox_props = dict(boxstyle="round,pad=0.3", facecolor='white',
                              alpha=0.9, edgecolor='black', linewidth=1)
            fontweight = 'normal'
            fontsize = 8

        ax.annotate(label,
                    (detector['sumo_x'], detector['sumo_y']),
                    xytext=(0, 0), textcoords='offset points',
                    fontsize=fontsize, ha='center', va='center',
                    bbox=bbox_props,
                    fontweight=fontweight,
                    zorder=10)

    ax.set_xlabel('X coordinate (m)', fontsize=12)
    ax.set_ylabel('Y coordinate (m)', fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.axis('equal')

    # Add text box with statistics
    stats_text = f"Total Detectors: {len(all_detectors)}\n"
    stats_text += f"Selected: {len(selected)}\n"
    stats_text += f"Available: {len(unselected)}\n"
    stats_text += f"\nSelected Daily Flow: {selected['daily_flow'].sum():,.0f} veh/day\n"
    stats_text += f"Selected Avg Flow: {selected['daily_flow'].mean():,.0f} veh/day"

    if highlight_manually_added:
        stats_text += f"\n\nAuto-selected: {len(selected) - len(highlight_manually_added)}"
        stats_text += f"\nManually added: {len(highlight_manually_added)}"

    ax.text(0.02, 0.98, stats_text,
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.9))

    plt.tight_layout()
    return fig


def manual_detector_selection_enhanced(selected_auto, all_detectors, min_spacing=300):
    """
    Enhanced manual selection with flexible spacing constraints and better feedback.

    Args:
        selected_auto: DataFrame of automatically selected detectors
        all_detectors: DataFrame of all available detectors
        min_spacing: Default minimum spacing constraint (can be overridden)

    Returns:
        DataFrame combining auto-selected and manually selected detectors
    """
    print("\n" + "=" * 80)
    print("ENHANCED MANUAL DETECTOR ADDITION")
    print("=" * 80)

    # Show current selection
    print(f"\nCurrently auto-selected: {len(selected_auto)} detectors")
    print(f"Auto-selected daily flow: {selected_auto['daily_flow'].sum():,.0f} vehicles/day")
    print("\nYou can add as many additional detectors as needed.")

    # Create and show the first plot with ALL detector labels
    print("\nGenerating visualization with ALL detector IDs and counts...")
    fig1 = plot_all_detectors_with_labels(
        selected_auto, all_detectors,
        f"Step 1: Review ALL Detectors - {len(selected_auto)} Auto-Selected (see IDs and counts)"
    )
    plt.show()

    # Get available detectors
    available = all_detectors[~all_detectors['SiteID'].isin(selected_auto['SiteID'])].copy()
    available_sorted = available.sort_values('daily_flow', ascending=False)

    # Ask about spacing constraint preference
    print("\n" + "=" * 80)
    print("SPACING CONSTRAINT OPTIONS")
    print("=" * 80)
    print(f"Default minimum spacing is {min_spacing}m between detectors.")
    print("\nOptions:")
    print("  1. Enforce spacing constraint (detectors violating spacing will be skipped)")
    print("  2. Warn about spacing but allow addition")
    print("  3. Ignore spacing constraint completely")
    print("  4. Use custom spacing value")

    spacing_choice = input("\nChoose option (1-4, default=2): ").strip()

    enforce_spacing = False
    warn_spacing = True
    custom_spacing = min_spacing

    if spacing_choice == '1':
        enforce_spacing = True
        warn_spacing = False
        print(f"Will enforce {min_spacing}m minimum spacing")
    elif spacing_choice == '3':
        warn_spacing = False
        print("Ignoring spacing constraints")
    elif spacing_choice == '4':
        try:
            custom_spacing = float(input("Enter custom minimum spacing (meters): "))
            enforce_spacing = True
            warn_spacing = False
            print(f"Will enforce {custom_spacing}m minimum spacing")
        except ValueError:
            print(f"Invalid input, using default {min_spacing}m with warnings")
    else:  # Default to option 2
        print("Will warn about spacing violations but allow additions")

    # Show top available detectors
    print("\n" + "=" * 80)
    print("TOP 100 AVAILABLE DETECTORS BY DAILY FLOW")
    print("=" * 80)
    print(f"{'Rank':<6} {'SiteID':<10} {'Daily Flow':<12} {'Category':<10} {'X':<10} {'Y':<10}")
    print("-" * 70)

    for i, (_, det) in enumerate(available_sorted.head(100).iterrows(), 1):
        print(f"{i:<6} {int(det['SiteID']):<10} {int(det['daily_flow']):<12,} "
              f"{str(det['traffic_category']):<10} {det['sumo_x']:<10.1f} {det['sumo_y']:<10.1f}")

    print("\n" + "=" * 80)
    print("MANUAL SELECTION INPUT")
    print("=" * 80)
    print("Look at the plot above to see ALL detector locations with their IDs and daily counts.")
    print("Enter detector IDs to add manually (comma-separated).")
    print("You can add as many detectors as you want (no limit).")
    print("\nExamples of input formats:")
    print("  - Single: 1234")
    print("  - Multiple: 1234, 5678, 9012")
    print("  - Many: paste a long list separated by commas")

    # Show some actual available IDs as examples
    if len(available) > 0:
        example_ids = available_sorted.head(10)['SiteID'].astype(int).tolist()
        print(f"\nTop 10 available detector IDs by flow: {example_ids}")

    print("\nPress Enter to skip manual addition.")
    print("=" * 80)

    user_input = input("\nDetector IDs to add: ").strip()

    manually_added_ids = set()
    combined_selection = selected_auto.copy()
    spacing_violations = []

    if user_input:
        # Parse input (handle various formats)
        try:
            # Replace various separators with commas
            user_input = user_input.replace(';', ',').replace(' ', ',')
            # Split and parse
            input_ids = [int(id_str.strip()) for id_str in user_input.split(',') if id_str.strip()]

            print(f"\nProcessing {len(input_ids)} detector(s)...")

            added_count = 0
            skipped_spacing = 0
            not_found = 0
            already_selected = 0

            for det_id in input_ids:
                if det_id in available['SiteID'].values:
                    detector = available[available['SiteID'] == det_id].iloc[0]

                    # Check spacing constraint
                    min_dist_violation = None
                    if len(combined_selection) > 0:
                        for _, existing in combined_selection.iterrows():
                            dist = np.sqrt((detector['sumo_x'] - existing['sumo_x']) ** 2 +
                                           (detector['sumo_y'] - existing['sumo_y']) ** 2)
                            if dist < custom_spacing:
                                min_dist_violation = (int(existing['SiteID']), dist)
                                break

                    # Decide whether to add based on spacing policy
                    should_add = True
                    if min_dist_violation:
                        if enforce_spacing:
                            should_add = False
                            skipped_spacing += 1
                            print(f"  ✗ Detector {det_id}: Too close to detector {min_dist_violation[0]} "
                                  f"(distance: {min_dist_violation[1]:.0f}m < {custom_spacing}m) - SKIPPED")
                        elif warn_spacing:
                            spacing_violations.append((det_id, min_dist_violation[0], min_dist_violation[1]))
                            print(f"  ⚠ Detector {det_id}: Close to detector {min_dist_violation[0]} "
                                  f"(distance: {min_dist_violation[1]:.0f}m) - ADDED WITH WARNING")

                    if should_add:
                        combined_selection = pd.concat([combined_selection, detector.to_frame().T],
                                                       ignore_index=True)
                        manually_added_ids.add(det_id)
                        added_count += 1
                        if not min_dist_violation:
                            print(f"  ✓ Added detector {det_id} (flow: {int(detector['daily_flow']):,} vehicles/day)")
                else:
                    if det_id in selected_auto['SiteID'].values:
                        already_selected += 1
                        print(f"  ✗ Detector {det_id}: Already selected")
                    else:
                        not_found += 1
                        print(f"  ✗ Detector {det_id}: Not found in available detectors")

            print(f"\n" + "=" * 50)
            print(f"Manual Addition Summary:")
            print(f"  Successfully added: {added_count}")
            if skipped_spacing > 0:
                print(f"  Skipped (spacing): {skipped_spacing}")
            if not_found > 0:
                print(f"  Not found: {not_found}")
            if already_selected > 0:
                print(f"  Already selected: {already_selected}")
            if len(spacing_violations) > 0 and warn_spacing:
                print(f"  Added with spacing warnings: {len(spacing_violations)}")

        except ValueError as e:
            print(f"Error parsing input: {e}")
            print("No detectors added")
    else:
        print("\nNo manual additions requested")

    # Show summary
    print("\n" + "=" * 80)
    print("SELECTION SUMMARY")
    print("=" * 80)
    print(f"Auto-selected detectors: {len(selected_auto)}")
    print(f"Manually added detectors: {len(manually_added_ids)}")
    print(f"TOTAL selected detectors: {len(combined_selection)}")
    print(f"Total daily flow: {combined_selection['daily_flow'].sum():,.0f} vehicles/day")
    print(f"Average flow per detector: {combined_selection['daily_flow'].mean():,.0f} vehicles/day")

    if len(manually_added_ids) > 0:
        manual_detectors = combined_selection[combined_selection['SiteID'].isin(manually_added_ids)]
        print(f"\nManually added flow: {manual_detectors['daily_flow'].sum():,.0f} vehicles/day")
        print(f"Manually added detector IDs: {sorted(list(manually_added_ids))}")

    if len(spacing_violations) > 0 and warn_spacing:
        print(f"\n⚠ SPACING WARNINGS:")
        for det_id, close_to, distance in spacing_violations[:10]:  # Show first 10
            print(f"  Detector {det_id} is {distance:.0f}m from detector {close_to}")
        if len(spacing_violations) > 10:
            print(f"  ... and {len(spacing_violations) - 10} more warnings")

    return combined_selection, manually_added_ids


def save_results(selected, all_detectors, manually_added_ids=None):
    """Save the selected detector files with proper lane information"""

    # Get selected IDs
    selected_ids = set(selected['SiteID'].astype(str))

    # Load and filter original data
    df = pd.read_csv('filtered_detector_data.csv')

    # Remove Unnamed: 0 column if it exists (usually an unwanted index column)
    if 'Unnamed: 0' in df.columns:
        df.drop('Unnamed: 0', axis=1, inplace=True)
        print("  Removed 'Unnamed: 0' column")

    # Filter for selected detectors
    df['SiteID_str'] = df['SiteID'].astype(str)
    df_subset = df[df['SiteID_str'].isin(selected_ids)].copy()
    df_subset.drop('SiteID_str', axis=1, inplace=True)

    # IMPORTANT: Filter for October 9 only
    df_subset['Timestamp_parsed'] = pd.to_datetime(df_subset['Timestamp'])
    df_subset['date'] = df_subset['Timestamp_parsed'].dt.date
    oct9_date = pd.to_datetime('2024-10-09').date()

    # Keep only October 9 data
    before_filter = len(df_subset)
    df_subset = df_subset[df_subset['date'] == oct9_date].copy()
    after_filter = len(df_subset)

    # Remove the temporary date columns
    df_subset.drop(['Timestamp_parsed', 'date'], axis=1, inplace=True)

    print(f"  Filtered to October 9 only: {before_filter} → {after_filter} records")

    # Save files
    n = len(selected)

    # Add suffix for manually enhanced selection
    if manually_added_ids and len(manually_added_ids) > 0:
        suffix = f'{n}_stratified_manual'
    else:
        suffix = f'{n}_stratified_spaced'

    df_subset.to_csv(f'filtered_detector_data_{suffix}.csv', index=False)

    # Verify the date range in saved file
    timestamps = pd.to_datetime(df_subset['Timestamp'])
    print(f"  Date range in saved file: {timestamps.min()} to {timestamps.max()}")

    # Save mapping with updated columns including proper lane info
    # Essential columns
    essential_cols = ['detector_id', 'edge_id', 'sumo_x', 'sumo_y']

    # Lane-related columns (from fixed mapping)
    lane_cols = ['lane_id', 'lane_index', 'lane_distance', 'num_lanes',
                 'is_rightmost_lane', 'is_leftmost_lane']

    # Distance columns
    distance_cols = ['edge_distance', 'lane_distance']

    # Additional info columns
    info_cols = ['daily_flow', 'traffic_category', 'lane_width', 'lane_speed']

    # Build column list based on what's available
    mapping_cols = essential_cols.copy()
    for col_list in [lane_cols, distance_cols, info_cols]:
        for col in col_list:
            if col in selected.columns and col not in mapping_cols:
                mapping_cols.append(col)

    mapping_subset = selected[mapping_cols].copy()

    # Add a column to indicate manual selection
    if manually_added_ids:
        mapping_subset['selection_method'] = mapping_subset['detector_id'].apply(
            lambda x: 'manual' if int(float(x)) in manually_added_ids else 'auto'
        )

    # Rename daily_flow for clarity
    if 'daily_flow' in mapping_subset.columns:
        mapping_subset['daily_flow_oct9'] = mapping_subset['daily_flow']
        mapping_subset.drop('daily_flow', axis=1, inplace=True)

    mapping_subset.to_csv(f'detector_to_edge_mapping_{suffix}.csv', index=False)

    print(f"\nSaved files:")
    print(f"  - filtered_detector_data_{suffix}.csv")
    print(f"    Contains ONLY October 9, 2024 data")
    print(f"    {len(df_subset)} records for {n} detectors")
    print(f"  - detector_to_edge_mapping_{suffix}.csv")

    # Report what columns were saved
    print(f"\nMapping file includes:")
    for col in mapping_subset.columns:
        if col == 'lane_id':
            print(f"  - {col}: Actual nearest lane (not just lane_0)")
        elif col == 'lane_distance':
            print(f"  - {col}: Distance to assigned lane")
        elif col == 'lane_index':
            print(f"  - {col}: Lane number (0=rightmost)")
        elif col == 'selection_method':
            print(f"  - {col}: How detector was selected (auto/manual)")
        else:
            print(f"  - {col}")

    return n


def main():
    print("ENHANCED STRATIFIED DETECTOR SELECTION WITH FLEXIBLE MANUAL ADDITION")
    print("=" * 80)

    try:
        # Step 1: Run automatic selection with lane distance quality filtering
        # You can adjust the target count here
        print("\nStep 1: Automatic Selection")
        print("-" * 40)
        auto_target = input("Enter target for auto-selection (default=40): ").strip()
        if not auto_target:
            auto_target = 40
        else:
            auto_target = int(auto_target)

        selected_auto, all_detectors = select_stratified_detectors_with_spacing(
            target_count=auto_target,
            min_spacing=300,
            max_lane_distance=25  # Only include detectors within 25m of their lane
        )

        if len(selected_auto) == 0:
            print("\nERROR: No detectors selected automatically!")
            return 1

        # Step 2: Manual detector selection phase with enhanced options
        combined_selection, manually_added_ids = manual_detector_selection_enhanced(
            selected_auto, all_detectors,
            min_spacing=300  # Default spacing, can be overridden by user
        )

        # Step 3: Show final selection
        print("\n" + "=" * 80)
        print("CREATING FINAL VISUALIZATION")
        print("=" * 80)

        fig3 = plot_all_detectors_with_labels(
            combined_selection, all_detectors,
            f"Final Selection: {len(combined_selection)} detectors ({len(selected_auto)} auto + {len(manually_added_ids)} manual)",
            highlight_manually_added=manually_added_ids,
            show_all_labels=True  # Show all labels in final plot too
        )

        # Save the final visualization
        fig3.savefig('final_detector_selection.png', dpi=150, bbox_inches='tight')
        print("Saved final visualization: final_detector_selection.png")
        plt.show()

        # Save results
        n_saved = save_results(combined_selection, all_detectors, manually_added_ids)

        print("\n" + "=" * 80)
        print("SELECTION COMPLETE!")
        print("=" * 80)
        print(f"Total detectors selected: {len(combined_selection)}")
        if len(manually_added_ids) > 0:
            print(f"  - Auto-selected: {len(selected_auto)} (stratified with spacing)")
            print(f"  - Manually added: {len(manually_added_ids)} (your additions)")
        print(f"Total daily flow coverage: {combined_selection['daily_flow'].sum():,.0f} vehicles/day")
        print(f"Files saved with appropriate suffix")

        # Summary of lane mapping quality
        if 'lane_distance' in combined_selection.columns:
            print(f"\nLane mapping quality:")
            print(f"  Average distance to lane: {combined_selection['lane_distance'].mean():.1f}m")
            print(f"  Max distance to lane: {combined_selection['lane_distance'].max():.1f}m")
            excellent = (combined_selection['lane_distance'] <= 5).sum()
            good = ((combined_selection['lane_distance'] > 5) & (combined_selection['lane_distance'] <= 15)).sum()
            acceptable = (
                        (combined_selection['lane_distance'] > 15) & (combined_selection['lane_distance'] <= 25)).sum()
            print(f"  Excellent (<5m): {excellent} detectors")
            print(f"  Good (5-15m): {good} detectors")
            print(f"  Acceptable (15-25m): {acceptable} detectors")

        # Calculate final spacing statistics
        if len(combined_selection) > 1:
            coords = combined_selection[['sumo_x', 'sumo_y']].values
            dist_matrix = distance_matrix(coords, coords)
            np.fill_diagonal(dist_matrix, np.inf)
            min_distances = dist_matrix.min(axis=1)

            print(f"\nFinal Spacing Statistics:")
            print(f"  Minimum: {min_distances.min():.0f}m")
            print(f"  Average: {min_distances.mean():.0f}m")
            print(f"  Maximum: {min_distances.max():.0f}m")

            violations = (min_distances < 300).sum()
            if violations > 0:
                print(f"  Note: {violations} detector pairs are closer than 300m")

        return 0

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())