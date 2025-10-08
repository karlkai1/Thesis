Overview
This script identifies and removes duplicate geographic coordinates from a CSV file containing location data.
What It Does

Loads Data: Reads location data from output.csv
Identifies Duplicates:

Creates coordinate pairs by rounding sumo_x and sumo_y coordinates to 2 decimal places
Combines them into a unique key (format: x_y)
Identifies all rows that share the same coordinate pair


Reports Statistics:

Total number of rows in the original file
Number of rows with duplicate coordinates
Number of unique coordinate locations
Sample examples of duplicate coordinates (if any exist)


Creates Cleaned Datasets:

output_dedup.csv: Removes duplicate coordinates, keeping only the first occurrence of each unique location
output_dedup_reindexed.csv: Same as above, but with IDs reset to sequential numbers (0, 1, 2, ...)

Input Requirements

File named output.csv in the same directory
Must contain columns: id, sumo_x, sumo_y

Output Files

output_dedup.csv - Deduplicated data with original IDs preserved
output_dedup_reindexed.csv - Deduplicated data with sequential IDs
