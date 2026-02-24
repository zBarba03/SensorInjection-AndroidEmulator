#!/usr/bin/env python3

import argparse
import time
import csv
from sensormodel import getModel
from androidEmulator import send
import glob
import os

parser = argparse.ArgumentParser()
parser.add_argument("magnitude", choices=("Lower", "Normal", "Higher"))
parser.add_argument("frequency", type=int, help="injection frequency in hertz")
parser.add_argument("delay", choices=("Game", "Fastest"), help="android sensor delay (used only for csv logging)")
args = parser.parse_args()

S2NS = 1000000000
model = getModel(args.magnitude)
if(args.frequency == 0): period = None
else: period = S2NS / args.frequency

print(f"period (ns): {period}")

WRITE_LOGS = False if period is None else True

files = glob.glob(f"./send/{args.magnitude}_{args.frequency}_{args.delay}_send_*.csv")
iteration = len(files)
logFile = f"./send/{args.magnitude}_{args.frequency}_{args.delay}_send_{iteration}.csv"
print("writing to ", logFile)

if os.path.exists(logFile):
	print("error in iteration numbers, exiting")
	exit(1)

t0 = time.monotonic_ns()
now = t0
end = t0 + 10*S2NS
count = 0

with open(logFile, "w", newline="") as f:
	writer = csv.writer(f)
	writer.writerow(["timestamp", "ax", "ay", "az", "nano"])

	while end > now:
		now = time.monotonic_ns()
		[ax, ay, az] = model.value((now-t0)/S2NS)
		send(f"sensor set acceleration {ax}:{ay}:{az}", verbose=False)
		if(WRITE_LOGS):
			# timestamps always in millis since epoch
			# nano added for precision
			timestamp = int(time.time()*1000.0)
			writer.writerow([timestamp, ax, ay, az, now-t0])
		count += 1

		now = time.monotonic_ns()
		if(period != None ):
			target = t0 + count*period
			if now < target:
				time.sleep((target-now)/S2NS)
	if not WRITE_LOGS:
		writer.writerow([count])

if not WRITE_LOGS:
	print("total number of injections: ", count)
	print(f"estimated frequency: {count/10.0} Hz")