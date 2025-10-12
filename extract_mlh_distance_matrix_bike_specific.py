#!/usr/bin/env python3

from lxml import etree
import numpy as np
import pandas as pd
import re
import sumolib

# === CONFIGURATION ===
input_route_file = "mlh_trip_matrix_routes_BIKE.rou.xml"
network_file = "MUNET.net.xml"
output_matrix_file = "mlh_distance_matrix_BIKE.npy"
output_nodes_file = "mlh_node_ids_BIKE.txt"
output_csv_file = "mlh_distance_matrix_BIKE.csv"

print("=" * 70)
print("MLH DISTANCE MATRIX EXTRACTION")
print("=" * 70)

# Load network to calculate edge lengths
print("\n1. Loading network...")
net = sumolib.net.readNet(network_file)
print(f"   ✅ Network loaded: {network_file}")

# === PARSE XML ===
print("\n2. Loading route file...")
tree = etree.parse(input_route_file)
root = tree.getroot()
print(f"   ✅ Loaded: {input_route_file}")

# === FIRST PASS: IDENTIFY ACCESSIBLE POINTS ===
print("\n3. Identifying accessible delivery points...")

# Track which points can reach/return to MLH
can_reach_from_mlh = set()
can_return_to_mlh = set()
all_delivery_ids = set()

# Also collect all distances for later
distances = {}
route_count = 0
no_distance_count = 0

print("   Processing routes...")
for vehicle in root.findall("vehicle"):
    route_count += 1
    if route_count % 100000 == 0:
        print(f"   Processed {route_count:,} routes...")

    vid = vehicle.get("id")
    route = vehicle.find("route")

    if route is None or route.get("edges") is None:
        continue

    # Calculate route length
    edges = route.get("edges").split()
    length = 0.0

    # Try to get length from attribute first (if duarouter calculated it)
    route_length = route.get("length")
    if route_length:
        length = float(route_length)
    else:
        # Calculate manually from edges
        try:
            for edge_id in edges:
                edge = net.getEdge(edge_id)
                length += edge.getLength()
        except:
            no_distance_count += 1
            continue

    # Parse vehicle ID
    if vid.startswith("mlh_to_"):
        poi_id = int(vid.replace("mlh_to_", ""))
        can_reach_from_mlh.add(poi_id)
        all_delivery_ids.add(poi_id)
        distances[("mlh", poi_id)] = length

    elif vid.startswith("return_") and vid.endswith("_to_mlh"):
        match = re.match(r"return_(\d+)_to_mlh", vid)
        if match:
            poi_id = int(match.group(1))
            can_return_to_mlh.add(poi_id)
            all_delivery_ids.add(poi_id)
            distances[(poi_id, "mlh")] = length

    elif vid.startswith("del_"):
        match = re.match(r"del_(\d+)_to_(\d+)", vid)
        if match:
            from_id, to_id = map(int, match.groups())
            all_delivery_ids.update([from_id, to_id])
            distances[(from_id, to_id)] = length

print(f"   ✅ Processed {route_count:,} total routes")
if no_distance_count > 0:
    print(f"   ⚠️  Routes without distance data: {no_distance_count}")

# Find bidirectional points
bidirectional_points = can_reach_from_mlh.intersection(can_return_to_mlh)
one_way_problems = can_reach_from_mlh.symmetric_difference(can_return_to_mlh)

print(f"\n4. Accessibility Analysis:")
print(f"   Total delivery points found: {len(all_delivery_ids)}")
print(f"   Can reach from MLH: {len(can_reach_from_mlh)}")
print(f"   Can return to MLH: {len(can_return_to_mlh)}")
print(f"   Fully bidirectional: {len(bidirectional_points)}")
print(f"   Problematic points: {len(one_way_problems)}")

if one_way_problems:
    print(f"\n   ⚠️  Points with routing issues:")
    for problem_id in sorted(one_way_problems)[:10]:
        if problem_id in can_reach_from_mlh:
            print(f"      Point {problem_id}: MLH can reach, but cannot return")
        else:
            print(f"      Point {problem_id}: Cannot reach from MLH, but can return")
    if len(one_way_problems) > 10:
        print(f"      ... and {len(one_way_problems) - 10} more")

# === BUILD NODE LIST FOR VRP ===
# For MLH, we use single depot called 'mlh' instead of separate depot/depot_return
node_ids = ['mlh'] + sorted(list(bidirectional_points))
index_map = {node_id: idx for idx, node_id in enumerate(node_ids)}
N = len(node_ids)

print(f"\n5. Building distance matrix...")
print(f"   Matrix size: {N}x{N}")
print(f"   Nodes: 1 MLH depot + {N - 1} bidirectional delivery points")

# === BUILD MATRIX ===
matrix = np.full((N, N), np.inf)
np.fill_diagonal(matrix, 0)

# Fill matrix with distances
filled_entries = 0
missing_entries = 0

for (from_node, to_node), dist in distances.items():
    # Only include if both nodes are in our filtered set
    if from_node in index_map and to_node in index_map:
        i = index_map[from_node]
        j = index_map[to_node]
        matrix[i, j] = dist
        filled_entries += 1

# Check for missing entries in the matrix
for i in range(N):
    for j in range(N):
        if i != j and matrix[i, j] == np.inf:
            missing_entries += 1

print(f"\n6. Matrix Statistics:")
print(f"   Filled entries: {filled_entries:,}")
print(f"   Missing entries: {missing_entries:,}")
print(f"   Matrix density: {filled_entries / (N * N - N) * 100:.2f}%")

# Verify MLH connectivity
mlh_idx = 0
outbound_ok = sum(1 for i in range(1, N) if matrix[mlh_idx, i] != np.inf)
return_ok = sum(1 for i in range(1, N) if matrix[i, mlh_idx] != np.inf)

print(f"\n7. MLH Depot Connectivity:")
print(f"   MLH can reach: {outbound_ok}/{N - 1} delivery points")
print(f"   Can return to MLH: {return_ok}/{N - 1} delivery points")

if outbound_ok == return_ok == N - 1:
    print(f"   ✅ Perfect bidirectional connectivity!")
else:
    print(f"   ⚠️  Some connectivity issues remain")

# === SAVE OUTPUTS ===
# Save as numpy array
np.save(output_matrix_file, matrix)
print(f"\n8. Saving outputs...")
print(f"   ✅ Distance matrix: {output_matrix_file}")

# Save node IDs
with open(output_nodes_file, 'w') as f:
    for node in node_ids:
        f.write(f"{node}\n")
print(f"   ✅ Node IDs: {output_nodes_file}")

# Save as CSV for inspection
df = pd.DataFrame(matrix, index=node_ids, columns=node_ids)
df.to_csv(output_csv_file)
print(f"   ✅ CSV format: {output_csv_file}")

# === DISTANCE ANALYSIS ===
# Get finite distances for statistics
finite_distances = matrix[matrix != np.inf]
if len(finite_distances) > 0:
    # Separate MLH-related distances
    mlh_to_delivery = [matrix[0, i] for i in range(1, N) if matrix[0, i] != np.inf]
    delivery_to_mlh = [matrix[i, 0] for i in range(1, N) if matrix[i, 0] != np.inf]

    print(f"\n9. Distance Statistics:")
    print(f"   Overall:")
    print(f"     Average: {np.mean(finite_distances):.1f} meters")
    print(f"     Median: {np.median(finite_distances):.1f} meters")
    print(f"     Max: {np.max(finite_distances):.1f} meters")

    if mlh_to_delivery:
        print(f"\n   MLH → Delivery:")
        print(f"     Average: {np.mean(mlh_to_delivery):.1f} meters")
        print(f"     Max: {np.max(mlh_to_delivery):.1f} meters")
        print(f"     Over 3km: {sum(1 for d in mlh_to_delivery if d > 3000)} routes")
        print(f"     Over 5km: {sum(1 for d in mlh_to_delivery if d > 5000)} routes")

    if delivery_to_mlh:
        print(f"\n   Delivery → MLH:")
        print(f"     Average: {np.mean(delivery_to_mlh):.1f} meters")
        print(f"     Max: {np.max(delivery_to_mlh):.1f} meters")

print("\n" + "=" * 70)
print("✅ MLH DISTANCE MATRIX READY FOR VRP OPTIMIZATION!")
print("=" * 70)

print(f"\nMatrix summary:")
print(f"  - File: {output_matrix_file}")
print(f"  - Size: {N}x{N} ({N} locations)")
print(f"  - Contains: 1 MLH depot + {N - 1} delivery points")
print(f"  - All points are bidirectional (round trips guaranteed)")

print(f"\n🚴 Key insights for cargo bike operations:")
avg_dist_from_mlh = np.mean(mlh_to_delivery) if mlh_to_delivery else 0
if avg_dist_from_mlh > 0:
    if avg_dist_from_mlh < 2000:
        print(f"  ✅ Excellent MLH location! Average distance only {avg_dist_from_mlh:.0f}m")
    elif avg_dist_from_mlh < 3000:
        print(f"  ✅ Good MLH location. Average distance {avg_dist_from_mlh:.0f}m")
    else:
        print(f"  ⚠️  Some deliveries are far. Average distance {avg_dist_from_mlh:.0f}m")

print(f"\n📋 Next step: Run VRP optimization for cargo bikes (Step 8 MLH)")
print(f"   - Use appropriate vehicle capacity (15 packages)")
print(f"   - Consider cargo bike range constraints")
print(f"   - Optimize for different objectives (distance, time, emissions)")