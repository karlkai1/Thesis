#!/usr/bin/env python3
from lxml import etree

# Create configuration
config = etree.Element("configuration")

# Input files
input_elem = etree.SubElement(config, "input")
etree.SubElement(input_elem, "net-file", value="../../00_shared_data/network/MUNET.net.xml")
etree.SubElement(input_elem, "route-files", value="../route_files/status_quo_final_delivery_only.rou.xml,../../final_traffic_routes_fixed.rou.xml")
etree.SubElement(input_elem, "additional-files", value="../../detectors.add.xml")

# Output files
output_elem = etree.SubElement(config, "output")
etree.SubElement(output_elem, "tripinfo-output", value="../simulation_data/status_quo_realistic_traffic_tripinfo.xml")
etree.SubElement(output_elem, "summary-output", value="../simulation_data/status_quo_realistic_traffic_summary.xml")

# Time settings
time_elem = etree.SubElement(config, "time")
etree.SubElement(time_elem, "begin", value="0")
etree.SubElement(time_elem, "end", value="86400")

# Save to correct location
tree = etree.ElementTree(config)
tree.write('01_status_quo/simulation_config/status_quo_with_realistic_traffic.sumocfg',
           pretty_print=True, xml_declaration=True, encoding='UTF-8')
print("Created 01_status_quo/simulation_config/status_quo_with_realistic_traffic.sumocfg")