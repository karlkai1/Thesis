#!/usr/bin/env python3
"""
Step 10 MLH: Generate SUMO routes from cargo bike VRP solution
Creates route file with cargo bikes operating from MLH depot
"""

import pickle
from lxml import etree
import re
import pandas as pd

# MLH depot coordinates (from snapped location)
try:
    with open('mlh_depot_coords.txt', 'r') as f:
        coords = f.read().strip().split(',')
        mlh_depot_x = float(coords[0])
        mlh_depot_y = float(coords[1])
    print(f"Loaded MLH depot coordinates: ({mlh_depot_x:.2f}, {mlh_depot_y:.2f})")
except:
    # Fallback if file not found
    mlh_depot_x = 2000
    mlh_depot_y = 2535
    print(f"Warning: Using original MLH coordinates: ({mlh_depot_x}, {mlh_depot_y})")

print("\n" + "=" * 70)
print("MLH CARGO BIKE ROUTE GENERATION")
print("=" * 70)

# Load VRP solution
print("\n1. Loading cargo bike VRP solution...")
with open('mlh_vrp_solution_BIKE.pkl', 'rb') as f:
    vrp_data = pickle.load(f)

    if 'solution_data' in vrp_data:
        solution = vrp_data['solution_data']
        vrp_routes = solution['routes']
        nodes = solution['node_ids']
    else:
        vrp_routes = vrp_data['routes']
        nodes = vrp_data['nodes']

print(f"   Loaded {len(vrp_routes)} cargo bike routes")
print(f"   Total deliveries: {sum(r['deliveries'] for r in vrp_routes)}")
print(f"   Total distance: {sum(r['distance'] for r in vrp_routes) / 1000:.1f} km")

# Check VRP routes structure
if vrp_routes:
    print(f"\n   Sample route structure:")
    print(f"   First route nodes: {vrp_routes[0]['route_ids'][:5]}...{vrp_routes[0]['route_ids'][-2:]}")

# Load coordinates
print("\n2. Loading delivery coordinates...")
coord_map = {}
try:
    # Load from snapped POI file instead for accurate coordinates
    poi_tree = etree.parse('snapped_delivery_points_HYBRID.poi.xml')
    for poi in poi_tree.findall('.//poi'):
        if poi.get('id').startswith('dp_'):
            delivery_id = poi.get('id')[3:]  # Remove 'dp_' prefix
            coord_map[delivery_id] = {
                'x': float(poi.get('x')),
                'y': float(poi.get('y'))
            }
    print(f"   Loaded {len(coord_map)} delivery coordinates from POI file")
except Exception as e:
    print(f"   Warning: Could not load POI coordinates - {e}")
    # Fallback to CSV
    try:
        df = pd.read_csv('output_dedup_reindexed.csv')
        for _, row in df.iterrows():
            delivery_id = str(int(row['id']))
            coord_map[delivery_id] = {
                'x': float(row['sumo_x']),
                'y': float(row['sumo_y'])
            }
        print(f"   Loaded {len(coord_map)} delivery coordinates from CSV")
    except Exception as e2:
        print(f"   Error: Could not load coordinates - {e2}")

# Create routes
routes_root = etree.Element("routes")

# Add comment
comment = etree.Comment(
    f"MLH cargo bike routes - {len(vrp_routes)} bikes serving {sum(r['deliveries'] for r in vrp_routes)} deliveries. "
    f"MLH depot at: ({mlh_depot_x:.2f}, {mlh_depot_y:.2f})"
)
routes_root.append(comment)

# Process routes
print("\n3. Generating cargo bike trips...")
successful_routes = 0
failed_routes = 0
depart_time = 21600  # 6 AM start

for i, route_data in enumerate(vrp_routes):
    route_nodes = route_data['route_ids']

    # Skip empty routes
    if len(route_nodes) <= 2:
        print(f"   Skipping empty route {i}")
        continue

    # Verify route starts and ends with MLH
    if route_nodes[0] != 'mlh' or route_nodes[-1] != 'mlh':
        print(f"   ⚠️ Route {i} doesn't start/end at MLH: {route_nodes[0]} -> {route_nodes[-1]}")

    # Create trip that returns to depot
    trip = etree.SubElement(routes_root, "trip",
                            id=f"cargo_bike_{i}",
                            type="cargo_bike",
                            depart=str(int(depart_time)),
                            fromXY=f"{mlh_depot_x},{mlh_depot_y}",
                            toXY=f"{mlh_depot_x},{mlh_depot_y}")
    # Note: No 'via' parameter - let duarouter figure out the path

    # Add stops for deliveries (skip MLH at start and end)
    stops_added = 0
    for node_id in route_nodes[1:-1]:  # Skip first and last MLH
        if node_id in coord_map:
            coords = coord_map[node_id]
            etree.SubElement(trip, "stop",
                             x=str(coords['x']),
                             y=str(coords['y']),
                             duration="180",  # 3 minutes per stop
                             parking="true")
            stops_added += 1
        else:
            print(f"   ⚠️ No coordinates for delivery {node_id}")

    if stops_added > 0:
        successful_routes += 1
    else:
        failed_routes += 1
        print(f"   ❌ Route {i} has no valid stops")

    depart_time += 300  # 5 minutes between bike departures

# Save routes
output_file = 'mlh_vrp_trips_BIKE.xml'
tree = etree.ElementTree(routes_root)
tree.write(output_file, pretty_print=True, xml_declaration=True, encoding="UTF-8")

print(f"\n4. Route generation complete:")
print(f"   ✅ Created {output_file}")
print(f"   Successful routes: {successful_routes}")
print(f"   Failed routes: {failed_routes}")

print(f"\n📊 Summary:")
print(f"   Total cargo bikes: {successful_routes}")
total_deliveries = sum(r['deliveries'] for r in vrp_routes[:successful_routes])
print(f"   Total deliveries: {total_deliveries}")
if successful_routes > 0:
    print(f"   Average per bike: {total_deliveries / successful_routes:.1f} deliveries")

print(f"\n⏰ Deployment schedule:")
print(f"   First bike: 6:00 AM")
print(f"   Last bike: {6 + (successful_routes * 5 / 60):.1f} hours later")
print(f"   All bikes return to MLH depot after deliveries")

print(f"\n📋 Next step: Run duarouter to convert trips to routes")
print(f"\n" + "=" * 60)
print("Copy and run this command:")
print("=" * 60)
print(f"duarouter -n MUNET_EXTREME_bike.net.xml --route-files {output_file} \\")
print("  --additional-files cargo_bike_types.add.xml \\")
print("  -o mlh_vrp_final_BIKE.rou.xml \\")
print("  --ignore-errors --repair --routing-threads 8")
print("=" * 60)

print(f"\nThis will create mlh_vrp_final_BIKE.rou.xml for simulation")
print(f"Bikes will use ~70% bike lanes with the extreme network")