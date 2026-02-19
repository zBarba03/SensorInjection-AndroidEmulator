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
parser.add_argument("delay", choices=("DELAY-GAME", "DELAY-FASTEST"), help="android sensor delay (used only for csv logging)")
args = parser.parse_args()

model = getModel(args.magnitude)
if(args.frequency == 0): period = None
else: period = 1.0 / args.frequency # in seconds

WRITE_LOGS = False if period is None else True

files = glob.glob(f"../pythonLogs/{args.magnitude}_{args.frequency}_{args.delay}_send_*.csv")
iteration = len(files)
logFile = f"../pythonLogs/{args.magnitude}_{args.frequency}_{args.delay}_send_{iteration}.csv"
print("writing to ", logFile)

if os.path.exists(logFile):
	print("error in iteration numbers, exiting")
	exit(1)

t0 = time.time()
now = t0
end = t0 + 10.0
count = 0

with open(logFile, "w", newline="") as f:
	writer = csv.writer(f)
	writer.writerow(["timestamp", "ax", "ay", "az"])

	while end > now:
		beforeCalc = time.monotonic()
		[ax, ay, az] = model.value(now-t0)
		send(f"sensor set acceleration {ax}:{ay}:{az}", verbose=False)
		if(WRITE_LOGS):
			timestamp = int(now*1000.0)
			writer.writerow([timestamp, ax, ay, az])
		else: count += 1
		afterCalc = time.monotonic()

		if(period != None and afterCalc-beforeCalc < period):
			time.sleep(period - (afterCalc-beforeCalc))
		now = time.time()

if not WRITE_LOGS:
	print("total number of injections: ", count)
	print(f"estimated frequency: {count/10.0} Hz")

'''
t0_csv = None
t0_real = time.monotonic()
for row in reader:

	target_csv = int(row[ts_idx])
	if t0_csv == None:
		t0_csv = target_csv
	target_real = t0_real + (target_csv - t0_csv) / 1000.0
	now_real = time.monotonic()
	
	if target_real > now_real:
		time.sleep(target_real - now_real)
	
	#beforeInject = time.monotonic()
'''