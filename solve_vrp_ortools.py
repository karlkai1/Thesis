import numpy as np
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import json
import pickle
import time


def load_distance_matrix(matrix_file='distance_matrix_clean.npy',
                         node_file='node_ids_clean.txt'):
    """Load the CLEAN bidirectional distance matrix and node IDs"""
    print("Loading clean bidirectional distance matrix...")
    distance_matrix = np.load(matrix_file)

    with open(node_file, 'r') as f:
        node_ids = [line.strip() for line in f]

    # Keep original matrix for checking infinities
    original_matrix = distance_matrix.copy()

    # Convert to integers for OR-Tools
    distance_matrix_int = distance_matrix.astype(int)

    # Replace infinity with a large number
    MAX_DISTANCE = 99999999
    inf_mask = distance_matrix == np.inf
    inf_count = np.sum(inf_mask)
    if inf_count > 0:
        print(f"⚠️  Found {inf_count} infinite distances in matrix")
    distance_matrix_int[inf_mask] = MAX_DISTANCE

    return distance_matrix_int, node_ids, original_matrix


def check_route_validity(route_ids, node_ids, original_matrix):
    """Check if a route has any impossible consecutive connections"""
    node_to_idx = {node: i for i, node in enumerate(node_ids)}

    invalid_segments = []
    for i in range(len(route_ids) - 1):
        from_node = route_ids[i]
        to_node = route_ids[i + 1]

        from_idx = node_to_idx.get(from_node, -1)
        to_idx = node_to_idx.get(to_node, -1)

        if from_idx >= 0 and to_idx >= 0:
            if original_matrix[from_idx][to_idx] == np.inf:
                invalid_segments.append((i, from_node, to_node))

    return invalid_segments


def split_route_at_invalid_segments(route_data, node_ids, original_matrix):
    """Split a route into valid sub-routes at impossible connections"""
    route_ids = route_data['route_ids']
    invalid_segments = check_route_validity(route_ids, node_ids, original_matrix)

    if not invalid_segments:
        # Route is valid as-is
        return [route_data]

    print(f"  Vehicle {route_data['vehicle_id']}: Found {len(invalid_segments)} impossible connections")
    for seg_idx, from_node, to_node in invalid_segments:
        print(f"    Position {seg_idx}: {from_node} → {to_node} (impossible)")

    # Split the route into valid segments
    sub_routes = []
    last_split = 0

    for seg_idx, from_node, to_node in invalid_segments:
        if seg_idx > last_split:
            # Create a sub-route from last split to current position
            sub_route = route_ids[last_split:seg_idx + 1]

            # Ensure sub-route starts and ends with depot
            if sub_route[0] != 'depot':
                sub_route = ['depot'] + sub_route
            if sub_route[-1] != 'depot':
                sub_route = sub_route + ['depot']

            if len(sub_route) > 2:  # Only keep if has deliveries
                sub_routes.append({
                    'vehicle_id': f"{route_data['vehicle_id']}_part{len(sub_routes)}",
                    'route': route_data['route'][last_split:seg_idx + 1],
                    'route_ids': sub_route,
                    'deliveries': len(sub_route) - 2,
                    'is_partial': True,
                    'original_vehicle': route_data['vehicle_id']
                })

        last_split = seg_idx + 1

    # Add remaining segment after last split
    if last_split < len(route_ids) - 1:
        sub_route = route_ids[last_split:]
        if sub_route[0] != 'depot':
            sub_route = ['depot'] + sub_route
        if sub_route[-1] != 'depot':
            sub_route = sub_route + ['depot']

        if len(sub_route) > 2:
            sub_routes.append({
                'vehicle_id': f"{route_data['vehicle_id']}_part{len(sub_routes)}",
                'route': route_data['route'][last_split:],
                'route_ids': sub_route,
                'deliveries': len(sub_route) - 2,
                'is_partial': True,
                'original_vehicle': route_data['vehicle_id']
            })

    return sub_routes


def create_data_model(num_vehicles=15, vehicle_capacity=100):
    """Create the data model for VRP"""
    distance_matrix, node_ids, original_matrix = load_distance_matrix()

    print(f"\n✅ Loaded clean bidirectional matrix")
    print(f"   Matrix size: {len(distance_matrix)}x{len(distance_matrix)}")
    print(f"   Nodes: 1 depot + {len(node_ids) - 1} delivery points")

    data = {}
    data['distance_matrix'] = distance_matrix.tolist()
    data['num_vehicles'] = num_vehicles
    data['depot'] = 0
    data['vehicle_capacities'] = [vehicle_capacity] * num_vehicles
    data['node_ids'] = node_ids
    data['demands'] = [0] + [1] * (len(node_ids) - 1)
    data['original_matrix'] = original_matrix

    print(f"\nProblem size:")
    print(f"  Locations: {len(node_ids)} (1 depot + {len(node_ids) - 1} deliveries)")
    print(f"  Vehicles: {num_vehicles}")
    print(f"  Capacity per vehicle: {vehicle_capacity} deliveries")

    return data


def solve_vrp(data, time_limit_seconds=10):
    """Solve the VRP using OR-Tools"""
    print(f"\nSolving VRP (time limit: {time_limit_seconds}s)...")
    start_time = time.time()

    # Create the routing index manager
    manager = pywrapcp.RoutingIndexManager(
        len(data['distance_matrix']),
        data['num_vehicles'],
        data['depot']
    )

    # Create routing model
    routing = pywrapcp.RoutingModel(manager)

    # Distance callback
    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return data['distance_matrix'][from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Capacity constraint
    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return data['demands'][from_node]

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,
        data['vehicle_capacities'],
        True,
        'Capacity'
    )

    # Search parameters
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = time_limit_seconds

    # Solve
    solution = routing.SolveWithParameters(search_parameters)
    solve_time = time.time() - start_time
    print(f"Solving completed in {solve_time:.2f} seconds")

    if solution:
        return extract_solution(data, manager, routing, solution)
    else:
        print("No solution found!")
        return None


def extract_solution(data, manager, routing, solution):
    """Extract solution and handle impossible connections"""
    print("\nExtracting and validating solution...")

    routes = []
    for vehicle_id in range(data['num_vehicles']):
        route = []
        route_distance = 0
        index = routing.Start(vehicle_id)

        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            route.append(node_index)
            previous_index = index
            index = solution.Value(routing.NextVar(index))
            route_distance += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)

        # Add depot at end
        route.append(manager.IndexToNode(index))

        if len(route) > 2:  # More than just depot->depot
            route_node_ids = [data['node_ids'][idx] for idx in route]

            routes.append({
                'vehicle_id': vehicle_id,
                'route': route,
                'route_ids': route_node_ids,
                'distance': route_distance,
                'deliveries': len(route) - 2
            })

    print(f"  Initial routes: {len(routes)}")

    # Check and split routes with impossible connections
    print("\nChecking for impossible connections...")
    final_routes = []
    routes_with_issues = 0

    for route_data in routes:
        invalid_segments = check_route_validity(
            route_data['route_ids'],
            data['node_ids'],
            data['original_matrix']
        )

        if invalid_segments:
            routes_with_issues += 1
            # Split the route
            sub_routes = split_route_at_invalid_segments(
                route_data,
                data['node_ids'],
                data['original_matrix']
            )
            final_routes.extend(sub_routes)
            print(f"  Split vehicle {route_data['vehicle_id']} into {len(sub_routes)} sub-routes")
        else:
            final_routes.append(route_data)

    # Calculate statistics
    total_deliveries = sum(r['deliveries'] for r in final_routes)
    total_distance = sum(r.get('distance', 0) for r in final_routes if not r.get('is_partial', False))

    # Create solution summary
    solution_data = {
        'routes': final_routes,
        'num_vehicles_used': len(final_routes),
        'num_original_routes': len(routes),
        'routes_with_issues': routes_with_issues,
        'total_deliveries': total_deliveries,
        'total_distance': total_distance,
        'node_ids': data['node_ids']
    }

    # Print summary
    print(f"\n✅ Solution summary:")
    print(f"  Original routes: {len(routes)}")
    print(f"  Routes with impossible connections: {routes_with_issues}")
    print(f"  Final routes (after splitting): {len(final_routes)}")
    print(f"  Total deliveries covered: {total_deliveries}")

    if routes_with_issues > 0:
        print(f"\n📝 Split routes details:")
        for r in final_routes:
            if r.get('is_partial'):
                print(f"  {r['vehicle_id']}: {r['deliveries']} deliveries")

    return solution_data


def save_solution(solution_data, base_filename='vrp_solution_split'):
    """Save solution to files"""
    # Save as JSON
    json_file = f"{base_filename}.json"
    with open(json_file, 'w') as f:
        json.dump(solution_data, f, indent=2)
    print(f"\n✅ Solution saved to {json_file}")

    # Save as pickle
    pkl_file = f"{base_filename}.pkl"
    with open(pkl_file, 'wb') as f:
        pickle.dump({
            'routes': solution_data['routes'],
            'nodes': solution_data['node_ids'],
            'solution_data': solution_data
        }, f)
    print(f"✅ Also saved to {pkl_file}")


if __name__ == "__main__":
    print("=" * 60)
    print("VRP SOLVER WITH ROUTE SPLITTING FOR IMPOSSIBLE CONNECTIONS")
    print("=" * 60)

    # Create data model
    data = create_data_model(
        num_vehicles=15,
        vehicle_capacity=100
    )

    # Solve VRP
    solution = solve_vrp(data, time_limit_seconds=10)

    if solution:
        save_solution(solution, base_filename='vrp_solution_split')

        print("\n📋 Next steps:")
        print("  1. Update route generation to use vrp_solution_split.pkl")
        print("  2. Routes are already split to avoid impossible connections")
        print("  3. All routes should now work in duarouter!")