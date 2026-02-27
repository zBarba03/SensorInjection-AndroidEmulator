import os
import glob
import csv
import numpy as np
from utils import InterpolationModel

FREQ = 50
S2NS = 1000000000
PERIOD = S2NS // FREQ

files = sorted(glob.glob("fulldata/*.csv"))

for file in files:

    print("Processing:", file)

    model = InterpolationModel(file, kind="cubic")

    duration = model.duration_ns()
    t_values = np.arange(0, duration, PERIOD)

    outname = "i_" + os.path.basename(file)
    outfile = os.path.join("interp/", outname)

    with open(outfile, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "ax", "ay", "az", "nano"])

        for t in t_values:
            ax, ay, az = model.value_ns(t)

            timestamp = int(t / 1e6)

            writer.writerow([timestamp, ax, ay, az, t])