# generate_trip_matrix.py - Step 5: Generate all possible trip definitions

from lxml import etree
import time

# === CONFIGURATION ===
input_poi_file = "snapped_delivery_points_dedup.poi.xml"
output_trips_file = "trip_matrix_dedup_with_returns.xml"

# Depot coordinates
depot_exit_x = 3042.08
depot_exit_y = 5102.54
depot_return_x = 3054.28
depot_return_y = 5105.04

# Delivery stop duration (seconds)
DELIVERY_DURATION = 300  # 5 minutes

# === PARSE SNAPPED POIs ===
print("Loading POIs...")
start_time = time.time()

tree = etree.parse(input_poi_file)
root = tree.getroot()

# === FILTER DUPLICATE POI ENTRIES ===
print(f"Unfiltered POIs: {len(root.findall('poi'))}")
pois = []
seen_coords = set()

for poi in root.findall("poi"):
    poi_id = int(poi.get("id")[3:])  # Extract numeric ID
    x = float(poi.get("x"))
    y = float(poi.get("y"))

    coord = (round(x, 2), round(y, 2))
    if coord not in seen_coords:
        seen_coords.add(coord)
        pois.append((poi_id, x, y))

print(f"Filtered POIs: {len(pois)}")
print(f"This will generate {len(pois) + len(pois) ** 2 + len(pois)} trips total")

# === CREATE TRIPS ROOT ===
trips_root = etree.Element("routes")

# Add comment
comment = etree.Comment(
    f"Trip matrix with exact coordinate stops for VRP optimization: "
    f"{len(pois)} depot-to-delivery + {len(pois) ** 2} delivery-to-delivery + {len(pois)} delivery-to-depot trips. "
    f"Exit depot: ({depot_exit_x}, {depot_exit_y}), Return depot: ({depot_return_x}, {depot_return_y})"
)
trips_root.append(comment)

# === GENERATE DEPOT TO DELIVERY TRIPS ===
print("\nGenerating depot (exit) → delivery trips...")
depot_trips = 0

for poi_id, x, y in pois:
    trip = etree.SubElement(
        trips_root,
        "trip",
        id=f"depot_to_{poi_id}",
        type="delivery",
        depart="0.00",
        fromXY=f"{depot_exit_x},{depot_exit_y}",  # EXIT depot
        toXY=f"{x},{y}"
    )

    # Add stop at exact delivery coordinate
    etree.SubElement(
        trip,
        "stop",
        x=str(x),
        y=str(y),
        duration=str(DELIVERY_DURATION),
        parking="true"
    )

    depot_trips += 1

print(f"✅ Created {depot_trips} depot (exit) → delivery trips with stops")

# === GENERATE DELIVERY TO DELIVERY TRIPS ===
print("\nGenerating delivery → delivery trips...")
delivery_trips = 0
progress_interval = len(pois) // 10 if len(pois) > 10 else 1

for i, (from_id, from_x, from_y) in enumerate(pois):
    if i > 0 and i % progress_interval == 0:
        progress = (i / len(pois)) * 100
        print(f"  Progress: {progress:.0f}%...")

    for to_id, to_x, to_y in pois:
        # Skip self-loops
        if from_id == to_id:
            continue

        trip = etree.SubElement(
            trips_root,
            "trip",
            id=f"del_{from_id}_to_{to_id}",
            type="delivery",
            depart="0.00",
            fromXY=f"{from_x},{from_y}",
            toXY=f"{to_x},{to_y}"
        )

        # Add stop at exact destination coordinate
        etree.SubElement(
            trip,
            "stop",
            x=str(to_x),
            y=str(to_y),
            duration=str(DELIVERY_DURATION),
            parking="true"
        )

        delivery_trips += 1

print(f"✅ Created {delivery_trips} delivery → delivery trips with stops")

# === ADD RETURN TRIPS TO DEPOT ===
print("\nGenerating delivery → depot (return) trips...")
return_trips = 0

for poi_id, x, y in pois:
    trip = etree.SubElement(
        trips_root,
        "trip",
        id=f"return_{poi_id}_to_depot",
        type="delivery",
        depart="0.00",
        fromXY=f"{x},{y}",
        toXY=f"{depot_return_x},{depot_return_y}"  # RETURN depot!
    )

    # Note: No stop needed at depot (end of trip)

    return_trips += 1

print(f"✅ Created {return_trips} delivery → depot (return) trips")

# === ADD DEPOT TO DEPOT TEST TRIP ===
# This helps verify the depot-to-depot route works
print("\nAdding depot-to-depot test trip...")
test_trip = etree.SubElement(
    trips_root,
    "trip",
    id="depot_exit_to_return_test",
    type="delivery",
    depart="0.00",
    fromXY=f"{depot_exit_x},{depot_exit_y}",
    toXY=f"{depot_return_x},{depot_return_y}"
)
print("✅ Added depot-to-depot test trip")

# === WRITE TO FILE ===
print(f"\nWriting to {output_trips_file}...")
etree.ElementTree(trips_root).write(
    output_trips_file,
    pretty_print=True,
    xml_declaration=True,
    encoding="UTF-8"
)

# === SUMMARY ===
elapsed_time = time.time() - start_time
total_trips = depot_trips + delivery_trips + return_trips + 1  # +1 for test trip

print(f"\n📊 SUMMARY:")
print(f"✅ Created {output_trips_file}")
print(f"   Total trips: {total_trips:,}")
print(f"   - Depot (exit) → Delivery: {depot_trips:,}")
print(f"   - Delivery → Delivery: {delivery_trips:,}")
print(f"   - Delivery → Depot (return): {return_trips:,}")
print(f"   - Depot to Depot test: 1")
print(f"   Exit depot: ({depot_exit_x}, {depot_exit_y})")
print(f"   Return depot: ({depot_return_x}, {depot_return_y})")
print(f"   Time elapsed: {elapsed_time:.2f} seconds")

print("\n📋 NEXT STEPS:")
print("1. Run duarouter:")
print(f"   duarouter -n MUNET.net.xml --route-files {output_trips_file} \\")
print("     --additional-files vehicle_types.add.xml \\")
print("     -o trip_matrix_routes_with_returns.rou.xml \\")
print("     --route-length --routing-threads 8 --ignore-errors")
print("\n2. Check the output for return routes!")
print("   grep 'return_' trip_matrix_routes_with_returns.rou.xml | wc -l")
print("   Should see successful return routes")