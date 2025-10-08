Overview
This script snaps delivery point coordinates to the nearest drivable road lanes in a SUMO network, ensuring points are positioned on valid streets rather than floating in space.
What It Does

Loads Network Data:

Reads SUMO network file MUNET.net.xml containing road geometry
Loads delivery points from output_dedup_reindexed.csv


Finds Nearest Drivable Lanes:

For each delivery point, searches for lanes within 500 meters
Filters lanes to only include those that allow:

passenger vehicles
delivery vehicles
truck vehicles


Selects the closest drivable lane


Snaps Coordinates to Road:

Calculates the precise position on the lane closest to the original point
Updates coordinates to lie exactly on the lane geometry
Ensures points are on navigable roads for vehicle routing


Generates POI XML:

Creates <poi> elements with snapped coordinates
id: Formatted as dp_{number} (e.g., dp_0, dp_1)
type: Set to "delivery"
color: Green RGB (0,1,0) for visualization
Outputs to snapped_delivery_points_dedup.poi.xml


Error Handling:

Skips points with no nearby drivable lanes
Skips lanes with invalid geometry
Reports progress and issues for each point



Input Requirements

MUNET.net.xml - SUMO network file in the same directory
output_dedup_reindexed.csv - Delivery point coordinates

Must contain columns: id, sumo_x, sumo_y



Output

snapped_delivery_points_dedup.poi.xml - POI file with road-snapped coordinates
Console output showing success/failure for each point and summary statistics

Key Parameters

Search radius: 500 meters
Allowed vehicle classes: passenger, delivery, truck
Color: Green (0,1,0) to distinguish from pre-snapped points (light blue)
