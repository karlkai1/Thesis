import csv
import re


def utm_to_sumo(x, y, x_offset, y_offset):
    sumo_x = x - x_offset
    sumo_y = y - y_offset
    return sumo_x, sumo_y


def parse_point(point_str):
    match = re.match(r"POINT\s*\(([\d\.]+)\s+([\d\.]+)\)", point_str)
    if match:
        x = float(match.group(1))
        y = float(match.group(2))
        return x, y
    else:
        raise ValueError(f"Invalid point format: {point_str}")


def convert_csv(input_file, output_file):
    with open(input_file, newline="", encoding="utf-8") as data, open(
        output_file, "w", newline="", encoding="utf-8"
    ) as out_buff:
        reader = csv.DictReader(data)
        writer = csv.DictWriter(out_buff, fieldnames=list(["id", "sumo_x", "sumo_y"]))
        writer.writeheader()
        for row in reader:
            x, y = parse_point(row["destination"])
            sumo_x, sumo_y = utm_to_sumo(x, y, 685666.73, 5333180.50)

            # network area boundaries:
            if not (161.55 <= sumo_x <= 4838.98 and 149.12 <= sumo_y <= 5021.64):
                continue

            new_row = dict([("id", row["id"]), ("sumo_x", sumo_x), ("sumo_y", sumo_y)])
            writer.writerow(new_row)


if __name__ == "__main__":
    convert_csv("delivery_points_anonymized.csv", "output.csv")