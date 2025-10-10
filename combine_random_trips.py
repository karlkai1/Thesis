#!/usr/bin/env python3
"""
Combine multiple route files into candidate_routes.rou.xml for routeSampler
"""

import xml.etree.ElementTree as ET
import os
import sys


def combine_route_files():
    """Combine multiple route files into one"""

    print("=" * 80)
    print("COMBINING ROUTE FILES FOR ROUTESAMPLER")
    print("=" * 80)

    # List of route files to combine
    route_files = [
        'through_routes.rou.xml',
        'local_routes.rou.xml',
        'fringe_routes.rou.xml'
    ]

    # Create combined routes element
    combined = ET.Element('routes')
    combined.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
    combined.set('xsi:noNamespaceSchemaLocation', 'http://sumo.dlr.de/xsd/routes_file.xsd')

    total_vehicles = 0
    vehicle_id_counter = 0

    for route_file in route_files:
        if not os.path.exists(route_file):
            print(f"⚠️  {route_file} not found - skipping")
            continue

        print(f"\nProcessing {route_file}...")

        try:
            tree = ET.parse(route_file)
            root = tree.getroot()

            # Count and add vehicles/trips
            vehicles = root.findall('vehicle')
            trips = root.findall('trip')

            for vehicle in vehicles:
                # Renumber vehicle IDs to avoid conflicts
                vehicle.set('id', f'veh_{vehicle_id_counter}')
                combined.append(vehicle)
                vehicle_id_counter += 1

            for trip in trips:
                # Convert trips to vehicles if needed
                trip.set('id', f'veh_{vehicle_id_counter}')
                combined.append(trip)
                vehicle_id_counter += 1

            file_count = len(vehicles) + len(trips)
            total_vehicles += file_count
            print(f"  Added {file_count} vehicles/trips")

        except Exception as e:
            print(f"  Error reading {route_file}: {e}")

    # Write combined file
    if total_vehicles > 0:
        tree = ET.ElementTree(combined)
        output_file = 'candidate_routes.rou.xml'
        tree.write(output_file, encoding='utf-8', xml_declaration=True)

        print(f"\n✅ Created {output_file}")
        print(f"   Total vehicles: {total_vehicles}")
        print("\n📊 Next step: Run routeSampler (from 05_background_traffic directory)")
        print("   python $SUMO_HOME/tools/routeSampler.py \\")
        print("     -r candidate_routes.rou.xml \\")
        print("     -d counts.edgedata.xml \\")
        print("     -o calibrated_routes.rou.xml \\")
        print("     --optimize full \\")
        print("     --threads 8")
    else:
        print("\n❌ No vehicles found in any route files!")
        print("   Make sure to run randomTrips.py first to generate:")
        print("   - through_routes.rou.xml")
        print("   - local_routes.rou.xml")
        print("   - fringe_routes.rou.xml")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(combine_route_files())