import sumolib
import pandas as pd
from lxml import etree

# === FILE PATHS ===
net_file = "MUNET.net.xml"
delivery_csv = "output_dedup_reindexed.csv"
output_file = "snapped_delivery_points_dedup.poi.xml"

# === LOAD NETWORK ===
net = sumolib.net.readNet(net_file)

# === READ DELIVERY POINTS ===
df = pd.read_csv(delivery_csv)

# === XML ROOT CONTAINER ===
root = etree.Element("additional")

# === SNAP AND WRITE ===
skipped = 0

ALLOWED_CLASSES = {"passenger", "delivery", "truck"}

for _, row in df.iterrows():
    x, y = row["sumo_x"], row["sumo_y"]
    point_id = f"dp_{int(row['id'])}"

    neighbors = net.getNeighboringLanes(x, y, 500)
    drivable_neighbors = [
        (lane, dist)
        for lane, dist in neighbors
        if any(lane.allows(cls) for cls in ALLOWED_CLASSES)
    ]
    if neighbors:
        lane, dist = sorted(drivable_neighbors, key=lambda n: n[1])[0]
        lane_pos, _ = lane.getClosestLanePosAndDist((x, y))

        shape = lane.getShape()
        if shape and lane.getLength() > 0:
            snapped_x, snapped_y = sumolib.geomhelper.positionAtShapeOffset(
                shape, lane_pos
            )

            etree.SubElement(
                root,
                "poi",
                id=str(point_id),
                x=str(snapped_x),
                y=str(snapped_y),
                type="delivery",
                color="0,1,0",
            )

            print(f"✅ Snapped {point_id} to ({snapped_x:.2f}, {snapped_y:.2f})")
        else:
            print(f"⚠ Lane has no shape: {lane.getID()}")
            skipped += 1
    else:
        print(f"⚠ No lane found near point: {point_id}")
        skipped += 1

# === SAVE FILE ===
tree = etree.ElementTree(root)
tree.write(output_file, pretty_print=True, xml_declaration=True, encoding="UTF-8")

print(f"\n✅ Snapped POIs written to: {output_file}")
print(f"🚫 Skipped {skipped} points with no valid lane")
