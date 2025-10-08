UTM to SUMO Coordinate Converter

Overview
This script converts geographic coordinates from UTM (Universal Transverse Mercator) format to SUMO (Simulation of Urban MObility) coordinate system and filters locations within a specific network boundary.
What It Does

Reads Input Data:

Processes delivery_points_anonymized.csv
Extracts coordinates from destination column in POINT format (e.g., POINT(685828.28 5338202.14))


Coordinate Conversion:

Converts UTM coordinates to SUMO coordinates using offset values:

X offset: 685666.73
Y offset: 5333180.50


Formula: sumo_coordinate = utm_coordinate - offset


Boundary Filtering:

Only keeps locations within the SUMO network boundaries:

X range: 161.55 to 4838.98
Y range: 149.12 to 5021.64


Locations outside this area are excluded from the output

Generates Output:

Creates output.csv with three columns: id, sumo_x, sumo_y
Preserves original IDs from the input file

Input Requirements

File named delivery_points_anonymized.csv in the same directory
Must contain columns: id, destination
destination format: POINT(x y) where x and y are UTM coordinates

Output

output.csv - Contains only valid delivery points within the network boundaries
