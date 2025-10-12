Solves the Vehicle Routing Problem (VRP) specifically optimized for cargo bike deliveries from the MLH depot. It uses Google OR-Tools to find optimal delivery routes that respect cargo bike capacity and range constraints.

How It Works?

1. Data Loading:

Loads the distance matrix created by the previous extraction script
Loads node IDs (MLH depot + all delivery points)
Converts distances to integers for OR-Tools compatibility
Handles any remaining infinite distances by replacing them with a very large number

2. Cargo Bike Configuration:
Sets parameters specific to cargo bike operations:

Number of vehicles: 70 cargo bikes (more than vans due to lower capacity)
Vehicle capacity: 15 packages per bike (much lower than 100 for vans)
Max distance: 30,000 meters (30km range constraint per bike per day)
Demands: Each delivery point requires 1 package

3. VRP Problem Setup:
Creates a routing model with:

Distance callback: Retrieves travel distance between any two points
Capacity constraint: Ensures no bike carries more than 15 packages
Distance constraint: Ensures no bike exceeds 30km total route distance
Depot: MLH at index 0 (all routes start and end here)

4. Optimization Strategy:
Uses two-phase optimization:

Primary objective: Minimize number of bikes used (efficient resource utilization)
Secondary objective: Minimize total distance traveled
Search strategy: PATH_CHEAPEST_ARC with Guided Local Search metaheuristic
Time limit: 300 seconds (5 minutes) for finding solution

5. Solution Extraction:
For each bike that's used:

Extracts the complete route (sequence of delivery points)
Calculates route distance
Counts number of deliveries
Converts node indices to actual node IDs
Validates that routes don't exceed constraints

6. Solution Statistics:
Reports comprehensive metrics:

Number of bikes actually used vs. available
Total distance traveled by all bikes
Total deliveries completed
Average distance per bike
Average deliveries per bike
Longest single route
Whether any routes exceed the 30km range limit

7. Output Generation:
Saves solution in two formats:

JSON file: Human-readable with all route details and statistics
Pickle file: Python-serialized for pipeline compatibility with subsequent scripts

8. Sample Route Display:
Shows the first 5 routes as examples with their delivery counts and distances
Purpose in Your Thesis
This is the core optimization engine for the cargo bike scenario. It addresses the fundamental question: "How should cargo bikes be routed to efficiently deliver all packages while respecting their physical constraints?"
Key differences from van-based VRP:
Capacity:

Vans: ~100 packages → fewer vehicles, longer routes
Bikes: 15 packages → more vehicles, shorter routes

Range:

Vans: Essentially unlimited within urban area
Bikes: 30km constraint → forces route length consideration

Fleet size:

More bikes needed overall due to capacity limitations
But lower per-vehicle cost and environmental impact

Route characteristics:

Cargo bikes create many shorter, focused routes
Vans create fewer but longer comprehensive routes

Optimization focus:

Minimizes number of bikes first (resource efficiency)
Then minimizes distance (operational cost/time)
