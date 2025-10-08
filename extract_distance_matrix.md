Overview
This script extracts travel distances from SUMO route calculations and builds a clean distance matrix for VRP optimization by identifying and removing problematic delivery points that cause routing failures.
What It Does

Loads Network and POI Data:

Reads SUMO network file (MUNET.net.xml)
Loads snapped delivery points from POI file
Maps each delivery point to its nearest road edge


Identifies Problematic Edges:

Maintains a list of known problematic base edge IDs that cause routing issues
Maps delivery points located on these problematic edges
Tracks manually excluded points from failed vehicle routes


Analyzes Route Connectivity:
Parses trip_matrix_routes_with_returns.rou.xml to check every delivery point's connectivity:

Can reach from depot: Points accessible from exit depot
Can return to depot: Points that can route back to return depot
Bidirectional: Points with both capabilities (✅ required for VRP)
One-way traps: Reachable but cannot return
Unreachable: Can return but not reach
Isolated: No connections at all


Categorizes Problem Points:

Topology problems: One-way traps, unreachable, or isolated points
Edge problems: Points on known problematic edges (even if bidirectional)
Manual exclusions: Points from specific failing vehicle routes (e.g., vans 2 and 8)


Builds Clean Distance Matrix:

Creates N×N matrix where N = 1 depot + clean delivery points
Fills with actual route distances from SUMO calculations
Uses np.inf for impossible/missing routes
Diagonal set to 0 (no cost to stay at same location)


Extracts Route Distances:

Calculates total distance by summing edge lengths for each route
Stores distances for:

Depot → Delivery trips
Delivery → Delivery trips
Delivery → Depot return trips




Generates Multiple Output Formats:

NumPy binary (.npy): Fast loading for Python optimization
Text file: Node ID list for reference
CSV: Human-readable matrix format
Exclusion log: Detailed record of removed points and reasons



Input Requirements

trip_matrix_routes_with_returns.rou.xml - Calculated routes from duarouter
snapped_delivery_points_dedup.poi.xml - POI coordinates
MUNET.net.xml - SUMO network file

Output Files

distance_matrix_clean.npy - NumPy distance matrix (meters)
node_ids_clean.txt - Ordered list of node IDs
distance_matrix_clean.csv - Human-readable CSV format
excluded_points.txt - Log of removed points with categorized reasons

Key Parameters

Edge search radius: 10 meters for POI-to-edge mapping
Problematic edges: Hardcoded set of 15 known problematic base edge IDs
Manual exclusions: Points from failing vehicle routes (e.g., vans 2, 8)

Matrix Structure
           depot  point_1  point_2  ...  point_N
depot        0.0    d1      d2     ...    dN
point_1      d1'    0.0     d12    ...    d1N
point_2      d2'    d21     0.0    ...    d2N
...
point_N      dN'    dN1     dN2    ...    0.0

Values in meters
np.inf indicates impossible routes
Asymmetric matrix (d1 ≠ d1' due to one-way streets)

Quality Metrics Reported

Total delivery points analyzed
Bidirectional connectivity counts
Problem categories and counts
Final clean point count
Matrix density (percentage of filled entries)
Average distance statistics
Exclusion percentage

Usage
bashpython extract_distance_matrix_clean.py
Dependencies

lxml - XML parsing
numpy - Matrix operations
pandas - CSV export
sumolib - SUMO network utilities
re - Regular expressions for ID parsing

Problem Detection Strategy

Topology-based: Analyze actual route success/failure patterns
Edge-based: Remove points on known problematic road segments
Manual: Exclude specific points from empirically failing routes
Conservative approach: Better to exclude questionable points than risk solver failures

Note
This filtering process is critical for VRP solver success. The script aims for 100% routing success by removing approximately some of the problematic points. These were identified by trial and error, simply running the script raw at first, and then checking later if the duarouter script at the end fails, rather than risking solver failures on infeasible routes.
