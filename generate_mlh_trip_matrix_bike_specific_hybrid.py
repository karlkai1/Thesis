#!/usr/bin/env python3
"""
Step 6 MLH: Generate trip matrix for cargo bike operations from MLH depot
Similar to original Step 5 but adapted for MLH scenario
"""

from lxml import etree
import time

# === CONFIGURATION ===
input_poi_file = "snapped_delivery_points_HYBRID.poi.xml"
output_trips_file = "mlh_trip_matrix.xml"

# MLH depot coordinates (will be loaded from file)
try:
    with open('mlh_depot_coords.txt', 'r') as f:
        coords = f.read().strip().split(',')
        mlh_depot_x = float(coords[0])
        mlh_depot_y = float(coords[1])
        print(f"Loaded MLH depot coordinates from file: ({mlh_depot_x:.2f}, {mlh_depot_y:.2f})")
except:
    # Fallback to original coordinates if snapped file not found
    mlh_depot_x = 2000
    mlh_depot_y = 2535
    print(f"Warning: Using original MLH coordinates: ({mlh_depot_x}, {mlh_depot_y})")
    print("Run snap_mlh_depot.py first for accurate depot location!")

# Delivery stop duration (seconds) - can be shorter for cargo bikes
DELIVERY_DURATION = 180  # 3 minutes (vs 5 minutes for vans)

print("\n" + "=" * 70)
print("MLH TRIP MATRIX GENERATION")
print("=" * 70)

# === PARSE SNAPPED POIs ===
print("\nLoading delivery POIs...")
start_time = time.time()

tree = etree.parse(input_poi_file)
root = tree.getroot()

# === FILTER DUPLICATE POI ENTRIES ===
print(f"Unfiltered POIs: {len(root.findall('poi'))}")
pois = []
seen_coords = set()

for poi in root.findall("poi"):
    poi_id = int(poi.get("id")[3:])  # Extract numeric ID from "dp_X"
    x = float(poi.get("x"))
    y = float(poi.get("y"))

    coord = (round(x, 2), round(y, 2))
    if coord not in seen_coords:
        seen_coords.add(coord)
        pois.append((poi_id, x, y))

print(f"Filtered POIs: {len(pois)}")

# Calculate total trips
depot_to_delivery = len(pois)
delivery_to_delivery = len(pois) * (len(pois) - 1)  # No self-loops
delivery_to_depot = len(pois)
total_trips = depot_to_delivery + delivery_to_delivery + delivery_to_depot

print(f"\nTrip matrix will contain:")
print(f"  MLH → Delivery: {depot_to_delivery:,} trips")
print(f"  Delivery → Delivery: {delivery_to_delivery:,} trips")
print(f"  Delivery → MLH: {delivery_to_depot:,} trips")
print(f"  Total: {total_trips:,} trips")

# === CREATE TRIPS ROOT ===
trips_root = etree.Element("routes")

# Add comment
comment = etree.Comment(
    f"MLH trip matrix for cargo bike VRP optimization. "
    f"MLH depot at: ({mlh_depot_x:.2f}, {mlh_depot_y:.2f}). "
    f"Total trips: {total_trips:,} ({len(pois)} deliveries). "
    f"Delivery stop duration: {DELIVERY_DURATION}s"
)
trips_root.append(comment)

# === GENERATE MLH TO DELIVERY TRIPS ===
print("\nGenerating MLH → delivery trips...")
depot_trips = 0

for poi_id, x, y in pois:
    trip = etree.SubElement(
        trips_root,
        "trip",
        id=f"mlh_to_{poi_id}",
        type="cargo_bike",  # Using cargo bike type
        depart="0.00",
        fromXY=f"{mlh_depot_x},{mlh_depot_y}",
        toXY=f"{x},{y}"
    )

    # Add stop at exact delivery coordinate
    etree.SubElement(
        trip,
        "stop",
        x=str(x),
        y=str(y),
        duration=str(DELIVERY_DURATION),
        parking="true"  # Cargo bikes can park anywhere
    )

    depot_trips += 1

print(f"✅ Created {depot_trips} MLH → delivery trips")

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
            type="cargo_bike",
            depart="0.00",
            fromXY=f"{from_x},{from_y}",
            toXY=f"{to_x},{to_y}"
        )

        # Add stop at destination
        etree.SubElement(
            trip,
            "stop",
            x=str(to_x),
            y=str(to_y),
            duration=str(DELIVERY_DURATION),
            parking="true"
        )

        delivery_trips += 1

print(f"✅ Created {delivery_trips} delivery → delivery trips")

# === ADD RETURN TRIPS TO MLH ===
print("\nGenerating delivery → MLH return trips...")
return_trips = 0

for poi_id, x, y in pois:
    trip = etree.SubElement(
        trips_root,
        "trip",
        id=f"return_{poi_id}_to_mlh",
        type="cargo_bike",
        depart="0.00",
        fromXY=f"{x},{y}",
        toXY=f"{mlh_depot_x},{mlh_depot_y}"
    )

    # No stop needed at MLH (end of trip)

    return_trips += 1

print(f"✅ Created {return_trips} delivery → MLH return trips")

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
total_trips_created = depot_trips + delivery_trips + return_trips

print(f"\n📊 SUMMARY:")
print(f"✅ Created {output_trips_file}")
print(f"   Total trips: {total_trips_created:,}")
print(f"   - MLH → Delivery: {depot_trips:,}")
print(f"   - Delivery → Delivery: {delivery_trips:,}")
print(f"   - Delivery → MLH: {return_trips:,}")
print(f"   MLH depot location: ({mlh_depot_x:.2f}, {mlh_depot_y:.2f})")
print(f"   Stop duration: {DELIVERY_DURATION}s per delivery")
print(f"   Time elapsed: {elapsed_time:.2f} seconds")

print("\n🚴 KEY DIFFERENCES FROM STATUS QUO:")
print("   - Single depot location (no separate exit/return)")
print("   - Cargo bike vehicle type")
print("   - Shorter delivery stops (3 min vs 5 min)")
print("   - Central urban location vs warehouse")

print("\n📋 NEXT STEPS:")
print("1. Run duarouter to calculate distances:")
print(f"   duarouter -n MUNET_EXTREME_bike.net.xml --route-files {output_trips_file} \\")
print("     --additional-files cargo_bike_types.add.xml \\")
print("     -o mlh_trip_matrix_routes_BIKE.rou.xml \\")
print("     --route-length --routing-threads 8 --ignore-errors")
print("\n2. Extract distance matrix (Step 7 MLH)")
print("3. Run VRP optimization for cargo bikes")
print("\n💡 Note: Cargo bikes may have access to more paths (bike lanes, shortcuts)")
print("   that could result in shorter routes than delivery vans!")