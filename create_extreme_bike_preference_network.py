#!/usr/bin/env python3
# create_extreme_bike_preference_network.py
import sumolib

net = sumolib.net.readNet("../input/MUNET.net.xml")

with open("../output/extreme_bike_restrictions.edg.xml", "w") as f:
    f.write('<edges>\n')

    for edge in net.getEdges():
        edge_id = edge.getID()
        edge_type = edge.getType()

        if any(lane.allows("bicycle") for lane in edge.getLanes()):
            # Make ALL non-bike infrastructure EXTREMELY slow
            if edge_type in ["highway.primary", "highway.secondary", "highway.tertiary"]:
                f.write(f'    <edge id="{edge_id}" speed="0.3"/>\n')  # 1 km/h - walking pace
            elif edge_type == "highway.residential":
                f.write(f'    <edge id="{edge_id}" speed="0.5"/>\n')  # 1.8 km/h
            elif edge_type == "highway.service":
                f.write(f'    <edge id="{edge_id}" speed="0.8"/>\n')  # 2.9 km/h
            # Make bike paths much faster
            elif edge_type in ["highway.cycleway", "highway.path"]:
                f.write(f'    <edge id="{edge_id}" speed="15.0"/>\n')  # 54 km/h

    f.write('</edges>\n')

import subprocess

subprocess.run([
    "netconvert",
    "-s", "../input/MUNET.net.xml",
    "--edge-files", "../output/extreme_bike_restrictions.edg.xml",
    "-o", "../output/MUNET_EXTREME_bike.net.xml"
])

print("Created ../output/MUNET_EXTREME_bike.net.xml")