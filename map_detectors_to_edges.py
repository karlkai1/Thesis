#!/usr/bin/env python3
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

print(f"\nResults:")
print(f"  Total detectors: {len(results_df)}")
print(f"  Successfully mapped: {mapped}")
print(f"  Failed to map: {unmapped}")

if mapped > 0:
    print(f"\nDistance statistics for mapped detectors:")
    print(f"  Mean distance: {results_df['distance'].mean():.2f}m")
    print(f"  Max distance: {results_df['distance'].max():.2f}m")
    print(f"  Detectors within 25m: {(results_df['distance'] <= 25).sum()}")

print(f"\nSaved: detector_to_edge_mapping.csv")
