import csv
from lxml import etree

root = etree.Element("additional")

def convert_to_poi_xml(input_file, output_file):
    with open(input_file, newline="", encoding="utf-8") as data:
        reader = csv.DictReader(data)
        for row in reader:
            x = row["sumo_x"]
            y = row["sumo_y"]
            id = f"unsnap_dp_{int(row['id'])}"
            etree.SubElement(
                root,
                "poi",
                id=str(id),
                x=str(x),
                y=str(y),
                type="delivery",
                color="173,216,230"  # ✅ Add light blue color
            )
    tree = etree.ElementTree(root)
    tree.write(output_file, pretty_print=True, xml_declaration=True, encoding="UTF-8")

if __name__ == "__main__":
    convert_to_poi_xml("output_dedup_reindexed.csv", "points_pre_snap_dedup.poi.xml")