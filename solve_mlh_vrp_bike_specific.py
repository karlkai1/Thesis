import numpy as np
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import json
import time
import pickle


def load_mlh_distance_matrix(matrix_file='../vrp_optimization/mlh_distance_matrix_bike.npy',
                             node_file='../vrp_optimization/mlh_node_ids_bike.txt'):
    """Load the MLH distance matrix and node IDs"""
    print("Loading MLH distance matrix...")
    distance_matrix = np.load(matrix_file)

    with open(node_file, 'r') as f:
        node_ids = [line.strip() for line in f]

    # Convert to integers for OR-Tools
    distance_matrix_int = distance_matrix.astype(int)

    # Replace infinity with a large number (shouldn't be any in clean matrix)
    MAX_DISTANCE = 999999
    inf_count = np.sum(distance_matrix == np.inf)
    if inf_count > 0:
        print(f"⚠️  Warning: Found {inf_count} infinite distances!")
    distance_matrix_int[distance_matrix_int == np.inf] = MAX_DISTANCE

    return distance_matrix_int, node_ids


def create_data_model():
    """Create the data model for cargo bike VRP"""
    distance_matrix, node_ids = load_mlh_distance_matrix()

    # CARGO BIKE SPECIFIC PARAMETERS
    num_vehicles = 70  # More bikes needed due to lower capacity
    vehicle_capacity = 15  # Cargo bike capacity
    max_distance = 30000  # 30km max per bike per day (range constraint)

    print(f"\n✅ Loaded MLH distance matrix")
    print(f"   Matrix size: {len(distance_matrix)}x{len(distance_matrix)}")
    print(f"   Nodes: 1 MLH depot + {len(node_ids) - 1} delivery points")

    data = {}
    data['distance_matrix'] = distance_matrix.tolist()
    data['num_vehicles'] = num_vehicles
    data['depot'] = 0  # MLH is at index 0
    data['vehicle_capacities'] = [vehicle_capacity] * num_vehicles
    data['node_ids'] = node_ids
    data['demands'] = [0] + [1] * (len(node_ids) - 1)  # 0 for depot, 1 for deliveries
    data['max_distance'] = max_distance

    print(f"\n📊 Problem Configuration:")
    print(f"  Locations: {len(node_ids)} (1 MLH + {len(node_ids) - 1} deliveries)")
    print(f"  Vehicles: {num_vehicles} cargo bikes")
    print(f"  Capacity per bike: {vehicle_capacity} packages")
    print(f"  Max distance per bike: {max_distance / 1000:.0f} km")
    print(f"  Total deliveries: {len(node_ids) - 1}")
    print(f"  Min bikes needed: {(len(node_ids) - 1 + vehicle_capacity - 1) // vehicle_capacity}")

    return data


def solve_vrp(data, time_limit_seconds=300):
    """Solve the VRP using OR-Tools with cargo bike constraints"""
    print(f"\n🚴 Solving Cargo Bike VRP (time limit: {time_limit_seconds}s)...")
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

    # === CAPACITY CONSTRAINT ===
    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return data['demands'][from_node]

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,  # null capacity slack
        data['vehicle_capacities'],  # vehicle maximum capacities
        True,  # start cumul to zero
        'Capacity'
    )

    # === DISTANCE CONSTRAINT (Range limit for bikes) ===
    routing.AddDimension(
        transit_callback_index,
        0,  # no slack
        data['max_distance'],  # maximum distance per vehicle
        True,  # start cumul to zero
        'Distance'
    )

    # Get the distance dimension
    distance_dimension = routing.GetDimensionOrDie('Distance')

    # Try to minimize the number of vehicles first, then distance
    # This ensures we use bikes efficiently
    distance_dimension.SetGlobalSpanCostCoefficient(100)

    # Setting search parameters
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = time_limit_seconds

    # Solve the problem
    print("  Searching for optimal cargo bike routes...")
    print("  Constraints: capacity=15 packages, range=30km")
    solution = routing.SolveWithParameters(search_parameters)

    solve_time = time.time() - start_time
    print(f"  Solving completed in {solve_time:.2f} seconds")

    if solution:
        return extract_solution(data, manager, routing, solution)
    else:
        print("  ❌ No solution found!")
        print("  Try increasing number of vehicles or max distance")
        return None


def extract_solution(data, manager, routing, solution):
    """Extract and format the solution"""
    print("\n✅ Solution found!")

    routes = []
    total_distance = 0
    total_deliveries = 0
    max_route_distance = 0

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
            # Convert to actual node IDs
            route_node_ids = [data['node_ids'][idx] for idx in route]

            routes.append({
                'vehicle_id': vehicle_id,
                'route': route,
                'route_ids': route_node_ids,
                'distance': route_distance,
                'deliveries': len(route) - 2,
            })
            total_distance += route_distance
            total_deliveries += len(route) - 2
            max_route_distance = max(max_route_distance, route_distance)

    # Create solution summary
    solution_data = {
        'routes': routes,
        'num_vehicles_used': len(routes),
        'total_distance': total_distance,
        'total_deliveries': total_deliveries,
        'avg_distance_per_vehicle': total_distance / len(routes) if routes else 0,
        'avg_deliveries_per_vehicle': total_deliveries / len(routes) if routes else 0,
        'max_route_distance': max_route_distance,
        'node_ids': data['node_ids'],
        'vehicle_type': 'cargo_bike',
        'vehicle_capacity': data['vehicle_capacities'][0],
        'depot_type': 'mlh'
    }

    # Print summary
    print(f"\n📊 CARGO BIKE VRP SOLUTION:")
    print(f"  Bikes used: {len(routes)} out of {data['num_vehicles']}")
    print(f"  Total distance: {total_distance:,} meters ({total_distance / 1000:.1f} km)")
    print(f"  Total deliveries: {total_deliveries} out of {len(data['node_ids']) - 1}")
    print(f"  Average distance per bike: {solution_data['avg_distance_per_vehicle']:.0f}m")
    print(f"  Average deliveries per bike: {solution_data['avg_deliveries_per_vehicle']:.1f}")
    print(f"  Longest route: {max_route_distance:.0f}m ({max_route_distance / 1000:.1f}km)")

    # Check if any bike exceeds range
    over_range = sum(1 for r in routes if r['distance'] > data['max_distance'])
    if over_range > 0:
        print(f"  ⚠️  WARNING: {over_range} routes exceed 30km range limit!")
    else:
        print(f"  ✅ All routes within cargo bike range!")

    # Show first few routes
    print("\nSample routes (first 5):")
    for i, route_data in enumerate(routes[:5]):
        print(f"  Bike {route_data['vehicle_id']}: "
              f"{route_data['deliveries']} deliveries, "
              f"{route_data['distance'] / 1000:.1f}km")

    return solution_data


def save_solution(solution_data, base_filename='../vrp_optimization/mlh_vrp_solution_bike'):
    """Save solution to JSON and pickle files"""
    # Save as JSON for human reading
    json_file = f"{base_filename}.json"
    with open(json_file, 'w') as f:
        json.dump(solution_data, f, indent=2)
    print(f"\n✅ Solution saved to {json_file}")

    # Save as pickle for pipeline compatibility
    pkl_file = f"{base_filename}.pkl"
    with open(pkl_file, 'wb') as f:
        pickle.dump({
            'routes': solution_data['routes'],
            'nodes': solution_data['node_ids'],
            'solution_data': solution_data
        }, f)
    print(f"✅ Also saved to {pkl_file}")


if __name__ == "__main__":
    print("=" * 70)
    print("🚴 CARGO BIKE VRP OPTIMIZATION FOR MLH")
    print("=" * 70)

    # Create data model with cargo bike parameters
    data = create_data_model()

    # Solve VRP
    solution = solve_vrp(data, time_limit_seconds=300)  # 5 minute limit

    if solution:
        # Save solution
        save_solution(solution)

        print("\n📋 Next steps:")
        print("  1. Verify the solution makes sense for cargo bikes")
        print("  2. Generate SUMO routes (Step 10 MLH)")
        print("  3. Run simulation with cargo bikes")
        print("  4. Compare KPIs with delivery van scenario")

        print("\n💡 Key considerations for cargo bikes:")
        print("  - Shorter routes due to capacity (15 vs 100)")
        print("  - More vehicles needed but lower emissions")
        print("  - Better maneuverability in urban areas")
        print("  - No parking issues")
    else:
        print("\n❌ VRP optimization failed!")
        print("Consider:")
        print("  - Increasing number of vehicles")
        print("  - Increasing max distance per bike")
        print("  - Reducing time limit for faster (but less optimal) solution")