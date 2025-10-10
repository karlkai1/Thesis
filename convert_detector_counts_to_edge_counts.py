#!/usr/bin/env python3
"""
Step 4: Convert Detector Counts to Edge Counts for routeSampler
This version properly handles non-numeric values and updated column names
"""

import pandas as pd
import numpy as np
import xml.etree.ElementTree as ET
from xml.dom import minidom
import os
import sys
from datetime import datetime


def analyze_detector_data():
    """Analyze your detector data structure"""
    print("=" * 80)
    print("STEP 4.1: ANALYZING DETECTOR DATA")
    print("=" * 80)

    # Load detector data
    detector_file = 'filtered_detector_data_71_stratified_manual.csv'
    df = pd.read_csv(detector_file)

    df['Timestamp_parsed'] = pd.to_datetime(df['Timestamp'])
    df = df[df['Timestamp_parsed'].dt.date == pd.to_datetime('2024-10-09').date()]
    print(f"Filtered to October 9 only: {len(df)} records")

    print(f"Loaded: {detector_file}")
    print(f"Shape: {df.shape}")
    print(f"Columns: {df.columns.tolist()}")

    # CRITICAL FIX: Convert all flow columns to numeric IMMEDIATELY after loading
    print("\nConverting flow columns to numeric...")
    flow_cols = ['FlowRate_1', 'FlowRate_2', 'FlowRate_3',
                 'VehicleTypeFlow_1', 'VehicleTypeFlow_2', 'VehicleTypeFlow_3']
    for col in flow_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            print(f"  Converted {col}")

    # Parse timestamps
    df['Timestamp_parsed'] = pd.to_datetime(df['Timestamp'])
    df['hour'] = df['Timestamp_parsed'].dt.hour
    df['date'] = df['Timestamp_parsed'].dt.date

    print(f"\nTime range: {df['Timestamp_parsed'].min()} to {df['Timestamp_parsed'].max()}")
    print(f"Unique SiteIDs: {df['SiteID'].nunique()}")

    # Verify FlowRate_1 = FlowRate_2 + FlowRate_3
    df['flow_check'] = df['FlowRate_2'] + df['FlowRate_3']
    diff = (df['FlowRate_1'] - df['flow_check']).abs().mean()
    print(f"\nFlow verification (FlowRate_1 vs FlowRate_2+3): avg diff = {diff:.2f}")

    # Show vehicle type distribution
    total_vtype = df[['VehicleTypeFlow_1', 'VehicleTypeFlow_2', 'VehicleTypeFlow_3']].sum()
    if total_vtype.sum() > 0:
        print(f"\nVehicle type distribution:")
        print(
            f"  Type 1: {total_vtype['VehicleTypeFlow_1']:,.0f} ({100 * total_vtype['VehicleTypeFlow_1'] / total_vtype.sum():.1f}%)")
        print(
            f"  Type 2: {total_vtype['VehicleTypeFlow_2']:,.0f} ({100 * total_vtype['VehicleTypeFlow_2'] / total_vtype.sum():.1f}%)")
        print(
            f"  Type 3: {total_vtype['VehicleTypeFlow_3']:,.0f} ({100 * total_vtype['VehicleTypeFlow_3'] / total_vtype.sum():.1f}%)")
    else:
        print("\nNo vehicle type data found")

    return df


def check_existing_mapping():
    """Check the existing detector-to-edge mapping"""
    print("\n" + "=" * 80)
    print("STEP 4.2: CHECKING DETECTOR-EDGE MAPPING")
    print("=" * 80)

    mapping_file = 'detector_to_edge_mapping_71_stratified_manual.csv'
    if not os.path.exists(mapping_file):
        print(f"ERROR: {mapping_file} not found!")
        print("Run the edge mapping script first")
        return None

    mapping = pd.read_csv(mapping_file)
    print(f"Loaded: {mapping_file}")
    print(f"Available columns: {mapping.columns.tolist()}")
    print(f"Total detectors mapped: {len(mapping)}")
    print(f"Successfully mapped to edges: {mapping['edge_id'].notna().sum()}")

    # Check which distance column is available
    distance_col = None
    if 'edge_distance' in mapping.columns:
        distance_col = 'edge_distance'
    elif 'lane_distance' in mapping.columns:
        distance_col = 'lane_distance'
    elif 'distance' in mapping.columns:
        distance_col = 'distance'

    if distance_col:
        print(f"Average distance to edge/lane: {mapping[distance_col].mean():.2f}m")
        print(f"Max distance: {mapping[distance_col].max():.2f}m")
    else:
        print("Warning: No distance column found in mapping")

    # Check for lane column
    lane_col = None
    if 'lane_id' in mapping.columns:
        lane_col = 'lane_id'
    elif 'lane_0' in mapping.columns:
        lane_col = 'lane_0'

    if not lane_col:
        print("Warning: No lane column found in mapping")
        # Create a default lane column if missing
        mapping['lane_0'] = mapping['edge_id'].apply(lambda x: f"{x}_0" if pd.notna(x) else None)
        lane_col = 'lane_0'

    # Show sample mapping with available columns
    display_cols = ['detector_id', 'edge_id']
    if distance_col:
        display_cols.append(distance_col)
    if lane_col:
        display_cols.append(lane_col)

    print("\nSample mappings:")
    print(mapping[display_cols].head(5).to_string())

    # Store the lane column name for later use
    mapping['_lane_col'] = lane_col

    return mapping


def convert_to_dfrouter_format(df, mapping):
    """Convert to DFRouter format for edge data creation"""
    print("\n" + "=" * 80)
    print("STEP 4.3: CONVERTING TO DFROUTER FORMAT")
    print("=" * 80)

    # Fix detector ID format - convert both to integers then strings
    # Handle the .0 suffix in mapping file
    mapping['detector_id_clean'] = mapping['detector_id'].astype(float).astype(int).astype(str)
    mapped_detectors = set(mapping['detector_id_clean'])

    # Convert SiteID to string
    df['SiteID_str'] = df['SiteID'].astype(int).astype(str)
    data_detectors = set(df['SiteID_str'])

    # Find common detectors
    common_detectors = mapped_detectors & data_detectors

    print(f"Detectors in mapping: {len(mapped_detectors)}")
    print(f"  Sample mapping IDs: {list(mapped_detectors)[:5]}")
    print(f"Detectors in data: {len(data_detectors)}")
    print(f"  Sample data IDs: {list(data_detectors)[:5]}")
    print(f"Common detectors: {len(common_detectors)}")

    if len(common_detectors) == 0:
        print("\nDEBUGGING: Checking ID format mismatch...")
        print(f"First mapping ID type: {type(list(mapped_detectors)[0])}")
        print(f"First data ID type: {type(list(data_detectors)[0])}")

    # Filter data to common detectors
    df_filtered = df[df['SiteID_str'].isin(common_detectors)].copy()

    print(f"Filtered data records: {len(df_filtered)} (from {len(df)})")

    # Parse time - handle timezone-aware timestamps
    df_filtered['Timestamp_parsed'] = pd.to_datetime(df_filtered['Timestamp'])

    # Get first date and make it timezone-aware to match the data
    if len(df_filtered) > 0:
        first_timestamp = df_filtered['Timestamp_parsed'].min()
        # Create timezone-aware reference point at start of first day
        first_date = pd.Timestamp(first_timestamp.date(), tz=first_timestamp.tz)
        df_filtered['time_minutes'] = ((df_filtered['Timestamp_parsed'] - first_date) / pd.Timedelta(minutes=1)).astype(
            int)
    else:
        df_filtered['time_minutes'] = 0

    # Create DFRouter format
    rows = []
    for _, row in df_filtered.iterrows():
        # Use FlowRate_1 as total (it's already the sum)
        total_flow = int(row['FlowRate_1'])

        # Since VehicleTypeFlow columns are empty, use FlowRate_1 for cars
        # and assume no trucks (or split if you prefer)
        if row['VehicleTypeFlow_1'] > 0 or row['VehicleTypeFlow_2'] > 0:
            # Use vehicle type data if available
            qPKW = int(row['VehicleTypeFlow_1'])  # Cars
            qLKW = int(row['VehicleTypeFlow_2'])  # Trucks
        else:
            # No vehicle type data - put all in cars
            qPKW = total_flow  # All vehicles as cars
            qLKW = 0  # No trucks

        rows.append([
            str(row['SiteID']),
            int(row['time_minutes']),
            qPKW,
            qLKW,
            "",  # Speed (empty)
            ""  # Speed trucks (empty)
        ])

    flows_df = pd.DataFrame(rows, columns=['Detector', 'Time', 'qPKW', 'qLKW', 'vPKW', 'vLKW'])
    flows_df = flows_df.sort_values(['Detector', 'Time'])

    # Save detailed version
    flows_df.to_csv('flows_dfrouter.csv', sep=';', index=False)
    print(f"\nCreated: flows_dfrouter.csv")
    print(f"  Records: {len(flows_df)}")
    print(f"  Detectors: {flows_df['Detector'].nunique() if len(flows_df) > 0 else 0}")
    print(f"  Total vehicles: {(flows_df['qPKW'].sum() + flows_df['qLKW'].sum()) if len(flows_df) > 0 else 0:,}")

    # Create hourly aggregation
    if len(flows_df) > 0:
        flows_df['Hour'] = flows_df['Time'] // 60
        hourly = flows_df.groupby(['Detector', 'Hour']).agg({
            'qPKW': 'sum',
            'qLKW': 'sum'
        }).reset_index()
        hourly['Time'] = hourly['Hour'] * 60
        hourly['vPKW'] = ""
        hourly['vLKW'] = ""
        hourly = hourly[['Detector', 'Time', 'qPKW', 'qLKW', 'vPKW', 'vLKW']]
    else:
        hourly = pd.DataFrame(columns=['Detector', 'Time', 'qPKW', 'qLKW', 'vPKW', 'vLKW'])

    hourly.to_csv('flows_dfrouter_hourly.csv', sep=';', index=False)
    print(f"\nCreated: flows_dfrouter_hourly.csv (hourly aggregation)")
    print(f"  Hours: {hourly['Time'].nunique() if len(hourly) > 0 else 0}")
    print(f"  Total vehicles: {(hourly['qPKW'].sum() + hourly['qLKW'].sum()) if len(hourly) > 0 else 0:,}")

    return flows_df, hourly


def create_detector_definitions(mapping):
    """Create detector definition file for SUMO"""
    print("\n" + "=" * 80)
    print("STEP 4.4: CREATING DETECTOR DEFINITIONS")
    print("=" * 80)

    # Filter to mapped detectors with lanes
    mapped = mapping[mapping['edge_id'].notna()].copy()

    # Use the appropriate lane column
    if 'lane_id' in mapping.columns:
        mapped['lane_id'] = mapped['lane_id']
    elif 'lane_0' in mapping.columns:
        mapped['lane_id'] = mapped['lane_0']
    else:
        # Create default lane IDs from edge IDs
        mapped['lane_id'] = mapped['edge_id'].apply(lambda x: f"{x}_0" if pd.notna(x) else None)

    print(f"Creating definitions for {len(mapped)} detectors")

    root = ET.Element('additional')

    os.makedirs('output', exist_ok=True)

    for _, det in mapped.iterrows():
        e1 = ET.SubElement(root, 'e1Detector')
        # Convert detector_id to clean integer string format
        det_id = str(int(float(det['detector_id'])))
        e1.set('id', det_id)
        e1.set('lane', str(det['lane_id']))
        e1.set('pos', '20')  # Safe default position
        e1.set('freq', '3600')  # Hourly output
        e1.set('file', f"output/det_{det_id}.xml")

    # Save
    output_file = 'detectors_routesampler.add.xml'
    xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="    ")

    with open(output_file, 'w') as f:
        f.write(xml_str)

    print(f"Created: {output_file}")
    return output_file


def create_edge_data(hourly_flows, mapping):
    """Create edge data file for routeSampler"""
    print("\n" + "=" * 80)
    print("STEP 4.5: CREATING EDGE DATA")
    print("=" * 80)

    # Create detector to edge mapping - handle the float detector IDs
    # Convert mapping detector IDs to integers then strings to match flow data
    mapping['detector_id_clean'] = mapping['detector_id'].astype(float).astype(int).astype(str)
    det_to_edge = dict(zip(mapping['detector_id_clean'], mapping['edge_id']))

    # Aggregate flows by edge and time
    edge_counts = {}

    for _, row in hourly_flows.iterrows():
        det_id = str(row['Detector'])
        if det_id in det_to_edge:
            edge_id = det_to_edge[det_id]
            if pd.notna(edge_id):
                hour = int(row['Time'] / 60)
                count = row['qPKW'] + row['qLKW']

                key = (hour, edge_id)
                if key not in edge_counts:
                    edge_counts[key] = 0
                edge_counts[key] += count

    # Create XML
    root = ET.Element('meandata')

    if edge_counts:
        # Group by hour
        hours = sorted(set(h for h, e in edge_counts.keys()))

        for hour in hours:
            interval = ET.SubElement(root, 'interval')
            interval.set('begin', str(hour * 3600))
            interval.set('end', str((hour + 1) * 3600))

            # Add edges for this hour
            hour_edges = {e: c for (h, e), c in edge_counts.items() if h == hour}

            for edge_id, count in sorted(hour_edges.items()):
                edge = ET.SubElement(interval, 'edge')
                edge.set('id', edge_id)
                edge.set('entered', str(int(count)))

    # Save
    output_file = 'counts.edgedata.xml'
    xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="    ")

    with open(output_file, 'w') as f:
        f.write(xml_str)

    print(f"Created: {output_file}")
    print(f"  Hours: {len(set(h for h, e in edge_counts.keys())) if edge_counts else 0}")
    print(f"  Unique edges: {len(set(e for h, e in edge_counts.keys())) if edge_counts else 0}")
    print(f"  Total edge-hour combinations: {len(edge_counts)}")
    print(f"  Total vehicles: {sum(edge_counts.values()) if edge_counts else 0:.0f}")

    return output_file


def main():
    """Main execution"""
    print("STEP 4: PREPARING DATA FOR ROUTESAMPLER")
    print("=" * 80)
    print("This version properly handles non-numeric values and column names")
    print()

    try:
        # 4.1: Analyze detector data
        df = analyze_detector_data()

        # 4.2: Check existing mapping
        mapping = check_existing_mapping()
        if mapping is None:
            print("\n✗ Cannot proceed without detector-edge mapping")
            return 1

        # 4.3: Convert to DFRouter format
        flows, hourly_flows = convert_to_dfrouter_format(df, mapping)

        # 4.4: Create detector definitions
        detector_file = create_detector_definitions(mapping)

        # 4.5: Create edge data
        edge_data_file = create_edge_data(hourly_flows, mapping)

        print("\n" + "=" * 80)
        print("STEP 4 COMPLETE!")
        print("=" * 80)
        print("\n✓ All files ready for routeSampler")
        print("\nGenerated files:")
        print(f"  1. flows_dfrouter_hourly.csv - Hourly detector flows")
        print(f"  2. {detector_file} - Detector definitions")
        print(f"  3. {edge_data_file} - Edge counts for routeSampler")
        print("\nStatistics:")
        print(f"  Detectors with data: {hourly_flows['Detector'].nunique()}")
        print(f"  Total hourly observations: {len(hourly_flows)}")
        print(f"  Total vehicles counted: {hourly_flows['qPKW'].sum() + hourly_flows['qLKW'].sum():,}")
        print("\nNext: Run Step 5 to build candidate route pool")

        return 0

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())