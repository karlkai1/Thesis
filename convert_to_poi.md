Overview
This script converts CSV coordinate data into SUMO POI (Point of Interest) XML format for visualization and simulation purposes.
What It Does

Reads Coordinate Data:

Processes output_dedup_reindexed.csv containing deduplicated delivery point coordinates


Generates XML Structure:

Creates a SUMO-compatible XML file with <additional> root element
Converts each CSV row into a <poi> (Point of Interest) element


POI Attributes:

id: Formatted as unsnap_dp_{number} (e.g., unsnap_dp_0, unsnap_dp_1)
x, y: SUMO coordinates from the CSV
type: Set to "delivery" for all points
color: Light blue RGB (173,216,230) for visualization


Creates Output:

Generates points_pre_snap_dedup.poi.xml
Pretty-printed XML with proper declaration and UTF-8 encoding
Ready to be imported into SUMO for network visualization



Input Requirements

File named output_dedup_reindexed.csv in the same directory
Must contain columns: id, sumo_x, sumo_y

Output

points_pre_snap_dedup.poi.xml - SUMO-compatible POI XML file
