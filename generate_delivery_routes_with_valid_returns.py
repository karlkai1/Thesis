import pickle
from lxml import etree
import pandas as pd

# Depot coordinates
depot_exit_x = 3042.08
depot_exit_y = 5102.54
depot_return_x = 3054.28
depot_return_y = 5105.04

print("\n" + "=" * 70)
print("DELIVERY VAN ROUTE GENERATION - DYNAMIC ROUTING")
print("=" * 70)

# Load VRP solution
print("\n1. Loading VRP solution...")
with open('vrp_solution_split.pkl', 'rb') as f:
    vrp_data = pickle.load(f)

    if 'solution_data' in vrp_data:
        solution = vrp_data['solution_data']
        vrp_routes = solution['routes']
        nodes = solution['node_ids']
    else:
        vrp_routes = vrp_data['routes']
        nodes = vrp_data['nodes']

print(f"   Loaded {len(vrp_routes)} routes")
print(f"   Total deliveries: {sum(r['deliveries'] for r in vrp_routes)}")

# Show ALL van routes
print("\n" + "=" * 70)
print("VAN ROUTES ANALYSIS")
print("=" * 70)

for van_id in range(len(vrp_routes)):
    route = vrp_routes[van_id]
    route_ids = route['route_ids'][1:-1]  # Skip depot at start/end
    print(f"\nVan {van_id}:")
    print(f"  Route length: {len(route_ids)} points")
    print(f"  Complete route: {route_ids}")

print("=" * 70)

# Load coordinates
print("\n2. Loading delivery coordinates...")
coord_map = {}
try:
    poi_tree = etree.parse('snapped_delivery_points_dedup.poi.xml')
    for poi in poi_tree.findall('.//poi'):
        if poi.get('id').startswith('dp_'):
            delivery_id = poi.get('id')[3:]
            coord_map[delivery_id] = {
                'x': float(poi.get('x')),
                'y': float(poi.get('y'))
            }
    print(f"   Loaded {len(coord_map)} delivery coordinates from POI file")
except Exception as e:
    print(f"   Warning: Could not load POI coordinates - {e}")

# Create routes
routes_root = etree.Element("routes")

comment = etree.Comment(
    f"Delivery van routes with dynamic routing - {len(vrp_routes)} vans serving {sum(r['deliveries'] for r in vrp_routes)} deliveries."
)
routes_root.append(comment)

# Vehicle type
etree.SubElement(routes_root, "vType",
                 id="delivery_van",
                 vClass="delivery",
                 length="7.5",
                 width="2.5",
                 maxSpeed="13.89",
                 color="255,0,0",
                 accel="2.6",
                 decel="4.5")

# Process routes
print("\n3. Generating van trips with dynamic routing...")
successful_routes = 0
failed_routes = 0
depart_time = 18000  # 5 AM start
STOP_DURATION = 300  # 5 minutes per delivery

for i, route_data in enumerate(vrp_routes):
    route_nodes = route_data['route_ids']

    if len(route_nodes) <= 2:
        print(f"   Skipping empty route {i}")
        continue

    if route_nodes[0] != 'depot' or route_nodes[-1] != 'depot':
        print(f"   ⚠️ Route {i} doesn't start/end at depot")
        continue

    stop_coords = []
    missing_coords = []

    for node_id in route_nodes[1:-1]:  # Skip depot nodes
        if node_id in coord_map:
            stop_coords.append(coord_map[node_id])
        else:
            missing_coords.append(node_id)

    if missing_coords:
        print(f"   ⚠️ Van {i}: Missing coordinates for {len(missing_coords)} stops")

    if stop_coords:
        trip = etree.SubElement(routes_root, "trip",
                                id=f"delivery_van_{i}",
                                type="delivery_van",
                                depart=str(int(depart_time)),
                                fromXY=f"{depot_exit_x},{depot_exit_y}",
                                toXY=f"{depot_return_x},{depot_return_y}")

        for coords in stop_coords:
            etree.SubElement(trip, "stop",
                             x=str(coords['x']),
                             y=str(coords['y']),
                             duration=str(STOP_DURATION),
                             parking="true")

        successful_routes += 1
        print(f"   ✅ Van {i}: {len(stop_coords)} stops out of {route_data['deliveries']} planned deliveries")
    else:
        failed_routes += 1
        print(f"   ❌ Van {i} has no valid stops")

    depart_time += 600

# Save routes
output_file = 'status_quo_delivery_dynamic.rou.xml'
tree = etree.ElementTree(routes_root)
tree.write(output_file, pretty_print=True, xml_declaration=True, encoding="UTF-8")

print(f"\n4. Route generation complete:")
print(f"   ✅ Created {output_file}")
print(f"   Successful routes: {successful_routes}")
print(f"   Failed routes: {failed_routes}")

print(f"\n📊 Summary:")
print(f"   Total vans: {successful_routes}")
total_deliveries = sum(r['deliveries'] for r in vrp_routes)
print(f"   Total planned deliveries: {total_deliveries}")
if successful_routes > 0:
    print(f"   Average per van: {total_deliveries / successful_routes:.1f} deliveries")

print(f"\n📋 Next step: Run duarouter to convert trips to routes")
print(f"\n" + "=" * 60)
print("Copy and run this command:")
print("=" * 60)
print(f"duarouter -n MUNET.net.xml --route-files {output_file} \\")
print("  --additional-files vehicle_types.add.xml \\")
print("  -o status_quo_final_dynamic.rou.xml \\")
print("  --ignore-errors --repair --remove-loops --routing-threads 8")
print("=" * 60)