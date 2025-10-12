## Main Purpose
Creates a **heavily modified version of the SUMO network** that artificially forces routing algorithms to strongly prefer bike infrastructure by making all other road types extremely slow.

## How It Works

**1. Network Analysis:**
- Reads the original SUMO network (`MUNET.net.xml`)
- Identifies all edges that allow bicycle traffic

**2. Speed Manipulation:**
Creates an edge modification file that dramatically alters speeds:

- **Primary/Secondary/Tertiary roads:** Set to 0.3 m/s (~1 km/h, crawling pace) - makes them essentially unusable
- **Residential streets:** Set to 0.5 m/s (~1.8 km/h, very slow walking pace) - strongly discourages use
- **Service roads:** Set to 0.8 m/s (~2.9 km/h, slow walking pace) - discourages use
- **Bike paths/cycleways:** Set to 15 m/s (~54 km/h, very fast) - strongly preferred

**3. Network Regeneration:**
- Uses SUMO's `netconvert` tool to apply these modifications
- Outputs a new network file: `MUNET_EXTREME_bike.net.xml`

## Purpose in the Paper
This creates an **extreme scenario** for testing bike delivery routing. Any routing algorithm using this network will:
- Avoid regular roads at almost any cost
- Take very long detours to stay on bike infrastructure
- Essentially simulate a "bikes-only" city scenario

This is likely used to establish an **upper bound** or **best-case scenario** for bike-based delivery performance - showing what would happen if cyclists had an extreme infrastructure advantage.
