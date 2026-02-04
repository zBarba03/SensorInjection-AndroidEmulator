#!/usr/bin/env python3

import argparse
import time
import csv
from sensormodel import getModel
from androidEmulator import send

parser = argparse.ArgumentParser()
parser.add_argument("magnitude", choices=("Lower", "Normal", "Higher"))
parser.add_argument("frequency", type=float, help="injection frequency in hertz")
args = parser.parse_args()

model = getModel(args.magnitude)
if(args.frequency == 10000):
	period = None
else:
	period = 1.0 / args.frequency # in seconds

t0 = time.time()
now = t0
end = t0 + 10.0
with open("latest_injection_log.csv", "w", newline="") as f:
	writer = csv.writer(f)
	writer.writerow(["Timestamp", "ax", "ay", "az"])

	while end > now:
		[ax, ay, az] = model.value(now-t0)
		send(f"sensor set acceleration {ax}:{ay}:{az}")
		timestamp = int(now*1000.0)
		writer.writerow([timestamp, ax, ay, az])
		if(period != None):
			time.sleep(period)
		now = time.time()