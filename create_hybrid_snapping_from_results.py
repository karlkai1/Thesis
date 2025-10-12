#!/usr/bin/env python3
# create_hybrid_snapping_from_results.py
from lxml import etree
import pandas as pd

# Step 1: Identify the problematic points
print("Identifying problematic points from distance matrix results...")

# Get all original points
df = pd.read_csv('output_dedup_reindexed.csv')
all_points = set(str(int(row['id'])) for _, row in df.iterrows())
print(f"Total original points: {len(all_points)}")

# Get the 908 bidirectional points
with open('mlh_node_ids_BIKE.txt', 'r') as f:
    bidirectional_points = set(line.strip() for line in f if line.strip() != 'mlh')
print(f"Bidirectional points: {len(bidirectional_points)}")

# Find the 28 problematic points
problematic_points = all_points - bidirectional_points
problematic_poi_ids = {f"dp_{p}" for p in problematic_points}
print(f"Problematic points to revert: {len(problematic_points)}")
print(f"Point IDs: {sorted(problematic_points)}")

# Step 2: Load both snapping versions
original_tree = etree.parse('snapped_delivery_points_dedup.poi.xml')
bike_tree = etree.parse('snapped_delivery_points_BIKE_PREFERRED.poi.xml')

# Build lookup for original positions
original_positions = {}
for poi in original_tree.findall('.//poi'):
    poi_id = poi.get('id')
    original_positions[poi_id] = {
        'x': poi.get('x'),
        'y': poi.get('y')
    }

# Step 3: Create hybrid snapping
root = etree.Element("additional")
reverted = 0
kept_bike = 0

for poi in bike_tree.findall('.//poi'):
    poi_id = poi.get('id')

    if poi_id in problematic_poi_ids:
        # Revert to original road snapping
        if poi_id in original_positions:
            x = original_positions[poi_id]['x']
            y = original_positions[poi_id]['y']
            color = "255,165,0"  # Orange for reverted
            reverted += 1
            print(f"Reverting {poi_id} to original position")
        else:
            # Shouldn't happen, but keep current if no original
            x = poi.get('x')
            y = poi.get('y')
            color = "255,0,0"  # Red
    else:
        # Keep bike lane snapping
        x = poi.get('x')
        y = poi.get('y')
        color = "0,255,0"  # Green for bike lane
        kept_bike += 1

    etree.SubElement(root, "poi",
                     id=poi_id,
                     x=x,
                     y=y,
                     type="delivery",
                     color=color)

# Save the hybrid file
tree = etree.ElementTree(root)
tree.write('snapped_delivery_points_HYBRID.poi.xml', pretty_print=True,
           xml_declaration=True, encoding='UTF-8')

print(f"\n✅ Created hybrid snapping:")
print(f"   Kept at bike lanes: {kept_bike} points")
print(f"   Reverted to roads: {reverted} points")
print(f"   Total: {kept_bike + reverted} points")
print(f"   Expected: 936 points")

# Step 4: Create verification script
print("\n📋 Next steps:")
print("1. Use snapped_delivery_points_HYBRID.poi.xml for trip matrix generation")
print("2. Regenerate from Step 7 onwards:")
print("   - python generate_mlh_trip_matrix.py (modify to use HYBRID file)")
print("   - duarouter with extreme network")
print("   - python extract_mlh_distance_matrix.py")
print("3. Verify you now have 936 bidirectional points")

# Save the problematic points for documentation
with open('problematic_bike_points.txt', 'w') as f:
    f.write("Points that couldn't be reached with bike lane snapping:\n")
    for p in sorted(problematic_points):
        f.write(f"{p}\n")

print(f"\nProblematic points saved to: problematic_bike_points.txt")
print("This documents which 28 points required road snapping for connectivity")