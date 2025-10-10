#!/usr/bin/env python3
"""
Convert detector coordinates from WGS84 (GeoJSON) to SUMO coordinates
Using the same UTM transformation as the delivery points script
"""

import json
import csv
import pandas as pd
import xml.etree.ElementTree as ET
from xml.dom import minidom

# Try to import pyproj for WGS84 to UTM conversion
try:
    from pyproj import Transformer

    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False
    print("Warning: pyproj not installed. Install with: pip install pyproj")

# Network offsets from your delivery script
X_OFFSET = 685666.73
Y_OFFSET = 5333180.50

# Network boundaries in SUMO coordinates
X_MIN, X_MAX = 161.55, 4838.98
Y_MIN, Y_MAX = 149.12, 5021.64


def wgs84_to_utm32n(lon, lat):
    """Convert WGS84 coordinates to UTM Zone 32N"""
    if HAS_PYPROJ:
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:32632", always_xy=True)
        x, y = transformer.transform(lon, lat)
        return x, y
    else:
        # Approximate conversion for Munich area (not accurate but gives an idea)
        # UTM Zone 32N central meridian is 9°E
        # This is VERY approximate and should only be used for testing
        x = (lon - 9.0) * 111000 * 0.64 + 500000  # Very rough approximation
        y = (lat - 0.0) * 111000 + 0
        print(f"Warning: Using approximate conversion for {lon}, {lat}")
        return x, y


def utm_to_sumo(x, y):
    """Convert UTM coordinates to SUMO local coordinates"""
    sumo_x = x - X_OFFSET
    sumo_y = y - Y_OFFSET
    return sumo_x, sumo_y


def load_geojson_detectors(geojson_file='detectors_in_study_area.geojson'):
    """Load detector positions from GeoJSON file"""

    print("=" * 80)
    print("LOADING GEOJSON DETECTORS")
    print("=" * 80)

    with open(geojson_file, 'r') as f:
        geojson_data = json.load(f)

    detectors = []
    for feature in geojson_data['features']:
        det_id = feature['properties']['detid']
        lon, lat = feature['geometry']['coordinates']
        detectors.append({
            'detector_id': str(det_id),
            'longitude': lon,
            'latitude': lat
        })

    print(f"  Loaded {len(detectors)} detectors from GeoJSON")

    return detectors


def convert_detector_coordinates(detectors):
    """Convert detector coordinates from WGS84 to SUMO"""

    print("\n" + "=" * 80)
    print("CONVERTING COORDINATES")
    print("=" * 80)

    print(f"  Using network offsets: X={X_OFFSET}, Y={Y_OFFSET}")
    print(f"  Network boundaries: X=[{X_MIN}, {X_MAX}], Y=[{Y_MIN}, {Y_MAX}]")

    converted = []
    in_bounds = 0
    out_bounds = 0

    for det in detectors:
        # Convert WGS84 to UTM Zone 32N
        utm_x, utm_y = wgs84_to_utm32n(det['longitude'], det['latitude'])

        # Convert UTM to SUMO coordinates
        sumo_x, sumo_y = utm_to_sumo(utm_x, utm_y)

        # Check if within network boundaries
        if X_MIN <= sumo_x <= X_MAX and Y_MIN <= sumo_y <= Y_MAX:
            converted.append({
                'detector_id': det['detector_id'],
                'longitude': det['longitude'],
                'latitude': det['latitude'],
                'utm_x': utm_x,
                'utm_y': utm_y,
                'sumo_x': sumo_x,
                'sumo_y': sumo_y,
                'in_bounds': True
            })
            in_bounds += 1
        else:
            converted.append({
                'detector_id': det['detector_id'],
                'longitude': det['longitude'],
                'latitude': det['latitude'],
                'utm_x': utm_x,
                'utm_y': utm_y,
                'sumo_x': sumo_x,
                'sumo_y': sumo_y,
                'in_bounds': False
            })
            out_bounds += 1

    print(f"\n  Conversion results:")
    print(f"    Total detectors: {len(converted)}")
    print(f"    Within network bounds: {in_bounds}")
    print(f"    Outside network bounds: {out_bounds}")

    # Show coordinate ranges
    df = pd.DataFrame(converted)
    in_bounds_df = df[df['in_bounds']]

    if len(in_bounds_df) > 0:
        print(f"\n  SUMO coordinate ranges (in-bounds only):")
        print(f"    X: {in_bounds_df['sumo_x'].min():.2f} to {in_bounds_df['sumo_x'].max():.2f}")
        print(f"    Y: {in_bounds_df['sumo_y'].min():.2f} to {in_bounds_df['sumo_y'].max():.2f}")

    return converted


def save_converted_coordinates(converted):
    """Save converted coordinates to CSV"""

    print("\n" + "=" * 80)
    print("SAVING CONVERTED COORDINATES")
    print("=" * 80)

    # Save all coordinates
    df = pd.DataFrame(converted)
    df.to_csv('detectors_all_coords.csv', index=False)
    print(f"  Saved: detectors_all_coords.csv (all {len(df)} detectors)")

    # Save only in-bounds detectors
    in_bounds_df = df[df['in_bounds']]
    in_bounds_df.to_csv('detectors_sumo_coords.csv', index=False)
    print(f"  Saved: detectors_sumo_coords.csv ({len(in_bounds_df)} in-bounds detectors)")

    # Create simple format for edge mapping
    simple_df = in_bounds_df[['detector_id', 'sumo_x', 'sumo_y']]
    simple_df.to_csv('detectors_for_edge_mapping.csv', index=False)
    print(f"  Saved: detectors_for_edge_mapping.csv (simplified format)")

    return in_bounds_df


def create_poi_visualization(in_bounds_df):
    """Create POI file for visualization in SUMO"""

    print("\n" + "=" * 80)
    print("CREATING POI VISUALIZATION")
    print("=" * 80)

    root = ET.Element('additional')

    for _, det in in_bounds_df.iterrows():
        poi = ET.SubElement(root, 'poi')
        poi.set('id', f"det_{det['detector_id']}")
        poi.set('x', str(det['sumo_x']))
        poi.set('y', str(det['sumo_y']))
        poi.set('color', '0,255,0,255')  # Green
        poi.set('width', '8')
        poi.set('height', '8')
        poi.set('layer', '100')
        poi.set('type', 'detector')

    # Format and save
    xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="    ")
    lines = [line for line in xml_str.split('\n') if line.strip()]

    with open('detector_pois_converted.add.xml', 'w') as f:
        f.write('\n'.join(lines))

    print(f"  Created: detector_pois_converted.add.xml")
    print(f"  Contains {len(in_bounds_df)} POIs")


def create_edge_mapping_script():
    """Create script to map detectors to network edges"""

    print("\n" + "=" * 80)
    print("CREATING EDGE MAPPING SCRIPT")
    print("=" * 80)

    script = """#!/usr/bin/env python3
'''
Map detectors to nearest edges using SUMO coordinates
'''

import sys
import os
import pandas as pd
sys.path.append(os.path.join(os.environ.get('SUMO_HOME', '/opt/homebrew/opt/sumo/share/sumo'), 'tools'))

try:
    import sumolib
except ImportError:
    print("Error: sumolib not found. Make sure SUMO_HOME is set correctly")
    sys.exit(1)

# Load network
print("Loading network...")
net = sumolib.net.readNet('00_shared_data/network/MUNET.net.xml')

# Load detector coordinates
print("Loading detector coordinates...")
detectors = pd.read_csv('detectors_for_edge_mapping.csv')

# Find nearest edges
print("Finding nearest edges...")
results = []

for idx, det in detectors.iterrows():
    x, y = det['sumo_x'], det['sumo_y']
    det_id = det['detector_id']

    # Find nearest edges within increasing radii
    for radius in [10, 25, 50, 100, 200]:
        nearby_edges = net.getNeighboringEdges(x, y, r=radius)

        if nearby_edges:
            # Get closest edge
            closest_edge, dist = min(nearby_edges, key=lambda x: x[1])
            lanes = closest_edge.getLanes()

            results.append({
                'detector_id': det_id,
                'sumo_x': x,
                'sumo_y': y,
                'edge_id': closest_edge.getID(),
                'distance': dist,
                'search_radius': radius,
                'num_lanes': len(lanes),
                'lane_0': lanes[0].getID() if lanes else None
            })
            break
    else:
        # No edge found even at 200m
        results.append({
            'detector_id': det_id,
            'sumo_x': x,
            'sumo_y': y,
            'edge_id': None,
            'distance': None,
            'search_radius': None,
            'num_lanes': 0,
            'lane_0': None
        })

    if (idx + 1) % 100 == 0:
        print(f"  Processed {idx + 1}/{len(detectors)} detectors...")

# Save results
results_df = pd.DataFrame(results)
results_df.to_csv('detector_to_edge_mapping.csv', index=False)

# Statistics
mapped = results_df['edge_id'].notna().sum()
unmapped = results_df['edge_id'].isna().sum()

print(f"\\nResults:")
print(f"  Total detectors: {len(results_df)}")
print(f"  Successfully mapped: {mapped}")
print(f"  Failed to map: {unmapped}")

if mapped > 0:
    print(f"\\nDistance statistics for mapped detectors:")
    print(f"  Mean distance: {results_df['distance'].mean():.2f}m")
    print(f"  Max distance: {results_df['distance'].max():.2f}m")
    print(f"  Detectors within 25m: {(results_df['distance'] <= 25).sum()}")

print(f"\\nSaved: detector_to_edge_mapping.csv")
"""

    with open('map_detectors_to_edges.py', 'w') as f:
        f.write(script)

    print("  Created: map_detectors_to_edges.py")


def create_verification_script():
    """Create script to verify detector positions"""

    script = """#!/bin/bash
# Verify detector positions in SUMO-GUI

echo "Opening SUMO-GUI with detector POIs..."
echo "Green dots show detector positions"
echo ""
echo "Check that detectors appear at intersections and major roads"

sumo-gui \\
  -n 00_shared_data/network/MUNET.net.xml \\
  -a detector_pois_converted.add.xml \\
  --window-size 1400,900 \\
  --delay 100

echo ""
echo "If positions look correct, run: python map_detectors_to_edges.py"
"""

    with open('verify_detector_positions.sh', 'w') as f:
        f.write(script)

    import os
    os.chmod('verify_detector_positions.sh', 0o755)
    print("  Created: verify_detector_positions.sh")


def main():
    print("DETECTOR COORDINATE CONVERSION (WGS84 → UTM → SUMO)")
    print("=" * 80)
    print("Using the same transformation as delivery points")
    print(f"Network offset: ({X_OFFSET}, {Y_OFFSET})")
    print("")

    # Load GeoJSON detectors
    detectors = load_geojson_detectors()

    # Convert coordinates
    converted = convert_detector_coordinates(detectors)

    # Save converted coordinates
    in_bounds_df = save_converted_coordinates(converted)

    # Create POI visualization
    if len(in_bounds_df) > 0:
        create_poi_visualization(in_bounds_df)

        # Create helper scripts
        create_edge_mapping_script()
        create_verification_script()

        print("\n" + "=" * 80)
        print("CONVERSION COMPLETE")
        print("=" * 80)

        print("\n✓ Successfully converted detector coordinates")
        print(f"✓ {len(in_bounds_df)} detectors within network bounds")

        print("\nNext steps:")
        print("1. Verify positions: ./verify_detector_positions.sh")
        print("2. If positions look correct, map to edges: python map_detectors_to_edges.py")
        print("3. This will create detector_to_edge_mapping.csv")
        print("4. Use the mapping to create detector definitions with lanes")
    else:
        print("\n⚠ WARNING: No detectors within network bounds!")
        print("Check if the offset values are correct")


if __name__ == "__main__":
    main()