import os
import glob
import csv
import numpy as np
from utils import InterpolationModel

INPUT_DIR = "fulldata/"
OUTPUT_DIR = "interp/"
FREQ = 50
MODEL_KIND = "cubic"

S2NS = 1_000_000_000
PERIOD = S2NS // FREQ

os.makedirs(OUTPUT_DIR, exist_ok=True)

files = sorted(glob.glob(INPUT_DIR + "*.csv"))

for file in files:

    print("Processing:", file)

    model = InterpolationModel(file, kind=MODEL_KIND)

    duration = model.duration_ns()
    t_values = np.arange(0, duration, PERIOD)

    outname = "i_" + os.path.basename(file)
    outfile = os.path.join(OUTPUT_DIR, outname)

    with open(outfile, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "ax", "ay", "az", "nano"])

        for t in t_values:
            ax, ay, az = model.value_ns(t)

            # timestamp in ms since epoch (same format as guide script)
            timestamp = int(t / 1e6)

            writer.writerow([timestamp, ax, ay, az, t])

    print("Written:", outfile)