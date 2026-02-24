#!/usr/bin/env python3

import argparse
import time
import csv
from utils import send
from utils import InterpolationModel
import glob
import os

parser = argparse.ArgumentParser()
parser.add_argument("file", help="path to CSV file")
parser.add_argument("frequency", type=int, help="interpolation frequency in hertz")
parser.add_argument("model", default="cubic", nargs="?", choices=("cubic","pchip"), help="cubic or pchip interpolation")
args = parser.parse_args()

dirPath = "/home/zbarba/uni/tesi/"
S2NS = 1000000000
model = InterpolationModel(args.file, kind=args.model)
if(args.frequency == 0): period = None
else: period = S2NS / args.frequency
print(f"period (ns): {period}")

# if args.frequency is 0 (max speed)
# the log csv file will only contain the total number of injections
# to calculate actual frequency.
WRITE_LOGS = False if period is None else True

# substitute origin "real"+model with "interp"+frequency
s = os.path.basename(args.file).split("_")
act = s[0]
pos = s[1]
delay = s[2] # sampling delay at time of recording
origin = s[3]
walkiter = s[4]
# = args.frequency # frequency after interpolation
name = f"interp/{act}_{pos}_{delay}_interp{args.frequency}_{walkiter}_"
repiter = len(glob.glob(dirPath + name + "*.csv"))
logFile = dirPath + name + f"{repiter}.csv"
print("writing to ", logFile)

if os.path.exists(logFile):
	print("error in iterations, exiting")
	exit(1)

t0 = time.monotonic_ns()
now = t0
end = t0 + model.duration_ns()
count = 0

with open(logFile, "w", newline="") as f:
	writer = csv.writer(f)
	writer.writerow(["timestamp", "ax", "ay", "az", "nano"])

	while now < end:
		[ax, ay, az] = model.value_ns(now-t0)
		send(f"sensor set acceleration {ax}:{ay}:{az}", verbose=False)
		if(WRITE_LOGS):
			# timestamps always in millis since epoch
			# nano added for additional precision
			timestamp = int(time.time()*1000.0)
			writer.writerow([timestamp, ax, ay, az, now-t0])
		count += 1
		now = time.monotonic_ns()
		if(period != None ):
			target = t0 + count*period
			if target < now: continue
			time.sleep((target-now)/S2NS)
			now = time.monotonic_ns()

	if not WRITE_LOGS:
		writer.writerow([count])

if not WRITE_LOGS:
	print("total number of injections: ", count)
	print(f"estimated frequency: {count/10.0} Hz")