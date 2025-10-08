Coordinate Transformation Details
WGS84 → UTM → SUMO (Three-Stage Conversion)

WGS84 to UTM Zone 32N (wgs84_to_utm32n)

Uses pyproj library with EPSG codes:

EPSG:4326 = WGS84 (standard GPS)
EPSG:32632 = UTM Zone 32N (Munich area)


UTM gives coordinates in meters, not degrees
Has a fallback approximation if pyproj isn't installed (very inaccurate, just for testing)
The approximation assumes central meridian at 9°E and uses rough meter conversions


UTM to SUMO Local (utm_to_sumo)

Subtracts fixed offsets: X_OFFSET = 685666.73, Y_OFFSET = 5333180.50
These offsets define where the SUMO network's origin (0,0) is in UTM coordinates
Result: coordinates relative to the network's local reference frame
This matches the delivery points script mentioned, ensuring consistency



Data Processing Flow
Loading Phase (load_geojson_detectors)
GeoJSON structure expected:
{
  "features": [
    {
      "properties": {"detid": "123"},
      "geometry": {"coordinates": [longitude, latitude]}
    }
  ]
}

Extracts detector ID and coordinates
Converts detector IDs to strings for consistency

Conversion Phase (convert_detector_coordinates)

Processes each detector through both transformations
Boundary checking logic: Uses rectangular bounds to filter detectors
Tracks statistics: in-bounds vs out-of-bounds counts
Stores complete coordinate chain: WGS84 → UTM → SUMO for traceability
Returns pandas DataFrame with in_bounds boolean flag

Why boundary checking matters:

SUMO networks are finite areas
Detectors outside the network can't be simulated
Need to know which real-world detectors correspond to the simulation area

Output Files Explained
1. CSV Files (save_converted_coordinates)

detectors_all_coords.csv: Complete audit trail with all coordinate systems
detectors_sumo_coords.csv: Production-ready filtered data
detectors_for_edge_mapping.csv: Minimal columns (id, x, y) for the next processing step

2. POI Visualization (create_poi_visualization)
xml<poi id="det_123" 
     x="1234.56" y="2345.67" 
     color="0,255,0,255"  
     width="8" height="8" 
     layer="100"  
     type="detector"/>

POI = Point of Interest in SUMO terminology
Green color chosen for visibility
Layer 100 ensures they render above roads
Size 8x8 pixels makes them visible but not overwhelming

Generated Helper Scripts
1. Edge Mapping Script (create_edge_mapping_script)
This is sophisticated - creates a Python script that:
python# Multi-radius search strategy
for radius in [10, 25, 50, 100, 200]:
    nearby_edges = net.getNeighboringEdges(x, y, r=radius)

Progressive search: Starts with 10m radius, expands if nothing found
Why? Detectors should be very close to roads, but GPS/conversion errors exist
Stops at first match (breaks loop) to prefer closest edges
Records which radius was needed (diagnostic info)

Lane information capture:

Gets number of lanes on matched edge
Stores first lane ID (lane_0) as default placement
Important because SUMO detectors must be assigned to specific lanes

Batch progress: Reports every 100 detectors to show it's working
2. Verification Script (create_verification_script)

Bash script to launch SUMO-GUI
Pre-configured window size (1400x900) for comfortable viewing
Sets delay=100ms for animation speed
Purpose: Visual QA - human checks if green dots align with roads/intersections

Design Patterns & Best Practices
Error Handling:

Try/except for pyproj import with graceful degradation
Checks for SUMO_HOME environment variable in generated script
Validates data availability before creating POI file

Reporting:

Section headers with "=" * 80 for readability
Progressive statistics: loaded → converted → saved
Coordinate range summaries for sanity checking

Workflow Guidance:
Next steps:
1. Verify positions: ./verify_detector_positions.sh
2. Map to edges: python map_detectors_to_edges.py
3. Create detector definitions

Clear pipeline for users
Each step validates before next
Separates concerns (coordinate conversion → visual check → edge matching)

Why This Approach?
Separation of coordinate conversion and edge matching:

Coordinate math is deterministic and fast
Edge matching requires loaded SUMO network (heavy)
Allows verification before expensive operations

Multiple output formats:

CSV for data processing
XML for SUMO visualization
Scripts for next steps
Each serves different user needs

Defensive programming:

Tracks in-bounds/out-bounds explicitly
Stores all intermediate coordinate systems
Provides diagnostic information (search radius, distances)

This script is part of a larger validation workflow where real-world traffic detector data needs to be integrated with a simulation, and accuracy is critical.
