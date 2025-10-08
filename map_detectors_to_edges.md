Script Architecture
SUMO Path Configuration
python
sys.path.append(os.path.join(os.environ.get('SUMO_HOME', '/opt/homebrew/opt/sumo/share/sumo'), 'tools'))
Breaking this down:

os.environ.get('SUMO_HOME', '/opt/homebrew/opt/sumo/share/sumo')
Tries to get SUMO_HOME environment variable
Falls back to macOS Homebrew default path
Issue: Windows/Linux users need different defaults
os.path.join(..., 'tools') adds the tools directory
sys.path.append() makes sumolib importable
Why needed?

SUMO's Python tools aren't installed via pip
They're distributed with SUMO installation
Must be manually added to Python path
Network Loading
python
net = sumolib.net.readNet('MUNET.net.xml')
What happens internally:

Parses entire XML network file
Builds spatial index of edges (likely R-tree or quad-tree)
Loads geometry of every edge, lane, junction
Memory intensive: large networks can use 100s of MBs
The .net.xml structure:

xml
<net>
  <edge id="edge1" from="junction1" to="junction2">
    <lane id="edge1_0" index="0" speed="13.89" length="100.0" shape="x1,y1 x2,y2 ..."/>
  </edge>
</net>
Core Algorithm: Progressive Radius Search
The Search Strategy
python
for radius in [10, 25, 50, 100, 200]:
    nearby_edges = net.getNeighboringEdges(x, y, r=radius)
    if nearby_edges:
        # Get closest edge
        closest_edge, dist = min(nearby_edges, key=lambda x: x[1])
        lanes = closest_edge.getLanes()
        # ... store and break
        break
Why progressive radiuses?

Efficiency: Most detectors are within 10m of a road
Don't waste time searching 200m if edge is 5m away
Early termination with break saves computation
Diagnostic information:
Records which radius succeeded (search_radius field)
Tells you data quality: many large radii = positioning problems
Reasonable limits:
10m: GPS accuracy under good conditions
25m: Typical GPS accuracy
50-100m: Poor GPS or coordinate conversion issues
200m: Last resort / something is wrong
Understanding getNeighboringEdges()
What it returns:

python
[(edge_object_1, distance_1), (edge_object_2, distance_2), ...]
Internal algorithm (conceptual):

Uses spatial index (R-tree) to quickly find candidate edges
For each candidate, calculates perpendicular distance from point to edge
Returns all edges within radius r
Distance is perpendicular distance, not Euclidean to endpoints
Why perpendicular distance matters:

Point P
  |
  | 5m (perpendicular distance)
  |
======Edge======
  50m           50m
Even though endpoints are 50m away, perpendicular distance is 5m
This is correct for detector placement
The min() Selection
python
closest_edge, dist = min(nearby_edges, key=lambda x: x[1])
Lambda breakdown:

nearby_edges is list of tuples: [(edge1, dist1), (edge2, dist2), ...]
key=lambda x: x[1] means "compare by second element (distance)"
Returns the tuple with smallest distance
Unpacks into closest_edge (object) and dist (float)
Edge case: What if multiple edges at same distance?

min() returns first one encountered
Could be at an intersection (multiple edges meet)
This is why recording search_radius helps diagnose ambiguity
Lane Extraction
python
lanes = closest_edge.getLanes()
# ...
'num_lanes': len(lanes),
'lane_0': lanes[0].getID() if lanes else None
SUMO lane numbering:

Lanes are numbered from right to left (right-hand traffic)
lane_0 is rightmost lane
Edge with 3 lanes: edge_0, edge_1, edge_2
Why store lane_0?

SUMO detectors must be placed on specific lanes, not just edges
Default choice: rightmost lane (typically slowest, most traffic)
User can manually reassign if needed
The defensive check:

python
lanes[0].getID() if lanes else None
Edges should always have lanes, but defensive programming
Could happen with pedestrian edges or edge types without lanes
Data Collection Strategy
Result Dictionary Structure
python
results.append({
    'detector_id': det_id,
    'sumo_x': x,
    'sumo_y': y,
    'edge_id': closest_edge.getID(),
    'distance': dist,
    'search_radius': radius,
    'num_lanes': len(lanes),
    'lane_0': lanes[0].getID() if lanes else None
})
Design decisions:

Includes original coordinates (sumo_x, sumo_y)
Allows verification/debugging
Can recalculate distances if needed
Records search radius
Quality metric: search_radius=10 is high confidence
search_radius=200 means manual review needed
Stores both edge and lane
Edge for logical grouping
Lane for actual detector placement
Number of lanes
Helps decide detector placement strategy
1 lane = simple, 4 lanes = need strategy for each
The Unmapped Case
python
else:  # for-else: no break occurred
    results.append({
        'detector_id': det_id,
        'sumo_x': x,
        'sumo_y': y,
        'edge_id': None,
        'distance': None,
        'search_radius': None,
        'num_lanes': 0,
        'lane_0': None
    })
Why store unmapped detectors?

Maintains consistent row count with input
Easy to identify problematic detectors
Can investigate: Are they in parks? Water? Outside network?
Alternative approach could be:

Skip unmapped detectors
Log to separate file
But current approach keeps everything together for analysis
Performance Analysis
Iteration Pattern
python
for idx, det in detectors.iterrows():
Known pandas anti-pattern:

iterrows() is slow (creates Series objects)
Better alternatives:
itertuples() (faster, creates namedtuples)
apply() (vectorized-ish)
Direct numpy array access
Why it's acceptable here:

Network loading is the bottleneck, not iteration
Each detector requires individual spatial search
Hard to vectorize spatial queries anyway
Readability > micro-optimization for this use case
Improved version would be:

python
for det in detectors.itertuples():
    x, y = det.sumo_x, det.sumo_y
    det_id = det.detector_id
Progress Reporting
python
if (idx + 1) % 100 == 0:
    print(f"  Processed {idx + 1}/{len(detectors)} detectors...")
Why every 100?

Not so frequent it spams console
Frequent enough to show progress (for 1000s of detectors)
idx + 1 because idx is 0-based
Limitation: No ETA calculation

Could add: time elapsed, rate, estimated time remaining
Statistical Analysis
Mapping Success Rate
python
mapped = results_df['edge_id'].notna().sum()
unmapped = results_df['edge_id'].isna().sum()
pandas pattern:

notna() returns boolean Series
.sum() counts True values (True = 1, False = 0)
Equivalent to: len(results_df[results_df['edge_id'].notna()])
Distance Statistics
python
print(f"  Mean distance: {results_df['distance'].mean():.2f}m")
print(f"  Max distance: {results_df['distance'].max():.2f}m")
print(f"  Detectors within 25m: {(results_df['distance'] <= 25).sum()}")
Quality indicators:

Mean < 15m: Excellent alignment
Mean 15-30m: Acceptable (typical GPS error)
Mean > 30m: Coordinate system problems
Max > 100m: Some detectors seriously misplaced
The within-25m metric:

(results_df['distance'] <= 25) creates boolean Series
.sum() counts how many True values
25m threshold = typical GPS accuracy
Potential Issues & Improvements
1. Variable Shadowing
python
closest_edge, dist = min(nearby_edges, key=lambda x: x[1])
Lambda parameter x shadows the coordinate x from outer scope
Works but confusing
Better: key=lambda item: item[1]
2. No Error Handling
python
net = sumolib.net.readNet('MUNET.net.xml')
detectors = pd.read_csv('detectors_for_edge_mapping.csv')
Files might not exist
CSV might be malformed
Should wrap in try-except
3. Memory Efficiency
python
results = []
# ... append to results ...
results_df = pd.DataFrame(results)
Builds entire list in memory
For 100k+ detectors, could use chunking
Or write to CSV incrementally
4. Hardcoded Filename
python
net = sumolib.net.readNet('MUNET.net.xml')
Should be command-line argument
Makes script reusable for other networks
5. No Detector Direction
Real detectors have direction (which way traffic flows)
Edges have direction in SUMO
Should check if detector faces same direction as edge
Might need to match edge or its reverse
6. Multi-lane Strategy
python
'lane_0': lanes[0].getID() if lanes else None
Always picks rightmost lane
What if detector is in left lane?
Could use position to determine which lane
Or create detector for all lanes
Output Format
CSV Structure
csv
detector_id,sumo_x,sumo_y,edge_id,distance,search_radius,num_lanes,lane_0
123,1000.5,2000.3,edge_45,5.2,10,2,edge_45_0
456,1500.7,2500.1,edge_67,15.8,25,3,edge_67_0
This enables:

Manual review in spreadsheet
Filtering by distance/radius
Creating SUMO detector definitions
Quality analysis
Integration with SUMO
Next steps would be:

Filter by distance threshold (e.g., keep only < 50m)
Generate SUMO detector XML:
xml
<additional>
  <e1Detector id="det_123" lane="edge_45_0" pos="50.0" freq="60" file="output.xml"/>
</additional>
Run simulation with detectors
Compare simulated vs real traffic counts
This script is the crucial bridge between real-world detector positions and SUMO's network topology.


