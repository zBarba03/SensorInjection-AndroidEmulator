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
parser.add_argument("frequency", type=float, help="injection frequency in hertz")
parser.add_argument("delay", choices=("DELAY-GAME", "DELAY-FASTEST"), help="android sensor delay (used only for csv logging)")
args = parser.parse_args()

model = getModel(args.magnitude)
if(args.frequency == 10000): period = None
else: period = 1.0 / args.frequency # in seconds

files = glob.glob(f"../pythonLogs/{args.magnitude}_{int(args.frequency)}_{args.delay}_send_*.csv")
iteration = len(files)
logFile = f"../pythonLogs/{args.magnitude}_{int(args.frequency)}_{args.delay}_send_{iteration}.csv"
print("writing to ", logFile)

if os.exists(logFile):
	print("error in iteration numbers, exiting")
	exit(1)


t0 = time.time()
now = t0
end = t0 + 10.0
with open(logFile, "w", newline="") as f:
	writer = csv.writer(f)
	writer.writerow(["timestamp", "ax", "ay", "az"])

	while end > now:
		[ax, ay, az] = model.value(now-t0)
		send(f"sensor set acceleration {ax}:{ay}:{az}")
		timestamp = int(now*1000.0)
		writer.writerow([timestamp, ax, ay, az])
		if(period != None):
			time.sleep(period)
		now = time.time()