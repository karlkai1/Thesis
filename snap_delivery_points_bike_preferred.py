#!/usr/bin/env python3
# snap_delivery_points_bike_preferred.py
import sumolib
import pandas as pd
from lxml import etree
import numpy as np

WALK_THRESHOLD = 30  # Maximum walking distance from bike lane to delivery
SEARCH_RADIUS = 50  # Initial search radius for bike lanes

net = sumolib.net.readNet("MUNET.net.xml")
df = pd.read_csv("output_dedup_reindexed.csv")

root = etree.Element("additional")
comparison_root = etree.Element("additional")  # For visualization

# Load original snapped points for comparison
original_tree = etree.parse("snapped_delivery_points_dedup.poi.xml")
original_coords = {}
for poi in original_tree.findall(".//poi"):
    if poi.get("id").startswith("dp_"):
        poi_id = poi.get("id")
        original_coords[poi_id] = (float(poi.get("x")), float(poi.get("y")))

# Statistics
snapped_to_bike = 0
kept_original = 0
movements = []

for _, row in df.iterrows():
    x, y = row["sumo_x"], row["sumo_y"]
    point_id = f"dp_{int(row['id'])}"

    # First check for nearby bike lanes
    bike_neighbors = []
    regular_neighbors = []

    neighbors = net.getNeighboringLanes(x, y, SEARCH_RADIUS)

    for lane, dist in neighbors:
        edge_type = lane.getEdge().getType()
        if lane.allows("bicycle"):
            if edge_type in ["highway.cycleway", "highway.path"]:
                if dist <= WALK_THRESHOLD:  # Only if walkable
                    bike_neighbors.append((lane, dist))
            else:
                regular_neighbors.append((lane, dist))

    # Decide where to snap
    if bike_neighbors:
        # Snap to nearest bike lane
        lane, dist = min(bike_neighbors, key=lambda x: x[1])
        snap_type = "bike_lane"
        snapped_to_bike += 1
    else:
        # Use original snapping
        if point_id in original_coords:
            snapped_x, snapped_y = original_coords[point_id]
            snap_type = "original"
            kept_original += 1
        else:
            # Fallback to nearest regular lane
            if regular_neighbors:
                lane, dist = min(regular_neighbors, key=lambda x: x[1])
                snap_type = "regular"
            else:
                continue

    # Calculate snapped position
    if snap_type != "original":
        lane_pos, _ = lane.getClosestLanePosAndDist((x, y))
        shape = lane.getShape()
        if shape and lane.getLength() > 0:
            snapped_x, snapped_y = sumolib.geomhelper.positionAtShapeOffset(shape, lane_pos)

    # Create POI
    poi = etree.SubElement(root, "poi",
                           id=point_id,
                           x=str(snapped_x),
                           y=str(snapped_y),
                           type="delivery")

    # Color based on type
    if snap_type == "bike_lane":
        poi.set("color", "0,255,0")  # Green for bike lanes
    else:
        poi.set("color", "255,0,0")  # Red for regular roads

    # Track movement for comparison
    if point_id in original_coords:
        old_x, old_y = original_coords[point_id]
        movement = np.sqrt((snapped_x - old_x) ** 2 + (snapped_y - old_y) ** 2)
        if movement > 0.1:
            movements.append((point_id, movement, snap_type))

            # Add comparison visualization
            # Original point (white)
            etree.SubElement(comparison_root, "poi",
                             id=f"{point_id}_OLD",
                             x=str(old_x),
                             y=str(old_y),
                             type="old_snap",
                             color="255,255,255",
                             layer="100")

            # New point (green or red)
            color = "0,255,0" if snap_type == "bike_lane" else "255,0,0"
            etree.SubElement(comparison_root, "poi",
                             id=f"{point_id}_NEW",
                             x=str(snapped_x),
                             y=str(snapped_y),
                             type="new_snap",
                             color=color,
                             layer="101")

            # Movement line (yellow)
            etree.SubElement(comparison_root, "poly",
                             id=f"{point_id}_move",
                             shape=f"{old_x},{old_y} {snapped_x},{snapped_y}",
                             color="255,255,0",
                             width="0.5",
                             layer="99")

# Save files
tree = etree.ElementTree(root)
tree.write("snapped_delivery_points_BIKE_PREFERRED.poi.xml", pretty_print=True,
           xml_declaration=True, encoding="UTF-8")

comparison_tree = etree.ElementTree(comparison_root)
comparison_tree.write("snapping_comparison_visual.poi.xml", pretty_print=True,
                      xml_declaration=True, encoding="UTF-8")

print(f"Snapping Results:")
print(f"  Snapped to bike lanes: {snapped_to_bike}")
print(f"  Kept original: {kept_original}")
print(f"  Bike lane percentage: {snapped_to_bike / (snapped_to_bike + kept_original) * 100:.1f}%")
print(f"\nLargest movements to bike lanes:")
movements.sort(key=lambda x: x[1], reverse=True)
for poi_id, dist, snap_type in movements[:5]:
    if snap_type == "bike_lane":
        print(f"  {poi_id}: moved {dist:.1f}m to bike lane")

print(f"\nVisualization saved to: snapping_comparison_visual.poi.xml")
print(f"View with: sumo-gui -n MUNET.net.xml -a snapping_comparison_visual.poi.xml")