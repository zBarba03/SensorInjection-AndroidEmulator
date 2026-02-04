#!/usr/bin/env python3

import csv
from androidEmulator import send
import time
import re
import argparse
from collections import deque
from scipy.interpolate import CubicSpline

parser = argparse.ArgumentParser()
parser.add_argument("-a", action="store_true", help="enable accelerometer")
parser.add_argument("-g", action="store_true", help="enable gyroscope")
parser.add_argument("-m", action="store_true", help="enable magnetic field")
parser.add_argument("csv_path", help="path to CSV file")
parser.add_argument("-r", type=int, default="1", help="number of repetitions of the csv file")
parser.add_argument("--period", type=float, help="interpolation with precise period of milliseconds")
parser.add_argument("-v", action="store_true", help="verbose sensor set")
args = parser.parse_args()

if not (args.a or args.g or args.m):
	ACC_ENABLED = GYRO_ENABLED = MAG_ENABLED = True
else:
	ACC_ENABLED = args.a
	GYRO_ENABLED = args.g
	MAG_ENABLED = args.m

ACC_ALIASES = {"ax", "accelerometerx", "accelerationx"}, \
			  {"ay", "accelerometery", "accelerationy"}, \
			  {"az", "accelerometerz", "accelerationz"}
GYR_ALIASES = {"gx", "gyroscopex", "rotationx"}, \
			  {"gy", "gyroscopey", "rotationy"}, \
			  {"gz", "gyroscopez", "rotationz"}
MAG_ALIASES = {"mx", "magnetometerx"}, \
			  {"my", "magnetometery"}, \
			  {"mz", "magnetometerz"}

# -------- csv header normalization --------
def normalize(col):
	return re.sub(r'[^a-z]', '', col.lower())

def find_indices(headers, groups):
	idx = []
	for g in groups:
		found = None
		for i, h in enumerate(headers):
			if normalize(h) in g:
				found = i
				break
		idx.append(found)
	return idx

def exact(reader, ts_idx, acc_idx, gyr_idx, mag_idx):
	print(f"using exact injection")
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
		if ACC_ENABLED and all(row[i]!='' for i in acc_idx):
			ax, ay, az = (row[i] for i in acc_idx)
			send(f"sensor set acceleration {ax}:{ay}:{az}")

		if GYRO_ENABLED and all(row[i]!='' for i in gyr_idx):
			gx, gy, gz = (row[i] for i in gyr_idx)
			send(f"sensor set gyroscope {gx}:{gy}:{gz}")

		if MAG_ENABLED and all(row[i]!='' for i in mag_idx):
			mx, my, mz = (row[i] for i in mag_idx)
			send(f"sensor set magnetic-field {mx}:{my}:{mz}")
		#afterInject = time.monotonic()
		#print(f"injection took {(afterInject-beforeInject)*1000} milliseconds")

#precondition: csv file has enough rows for the sliding window.
def interpolation(reader, ts_idx, acc_idx, gyr_idx, mag_idx):
	print(f"using cubic spline interpolation (only acceleration)")
	tsWindow = deque(maxlen=4)
	accWindow = deque(maxlen=4) #queue of xyz tuples

	startId = 1
	slideId = 2
	while len(tsWindow) < 4:
		row = next(reader)
		ts = int(row[ts_idx])
		acc = list(row[i] for i in acc_idx)
		tsWindow.append(ts)
		accWindow.append(acc)
	
	def slide(reader):
		try:
			row = next(
				row for row in reader
				if all(row[i] is not None for i in acc_idx)
			)
		except StopIteration:
			#print("no more rows")
			return False
		tsWindow.append(int(row[ts_idx]))
		accWindow.append(list(row[i] for i in acc_idx))
		return True
	
	#csv timestamps translated into real time
	t0 = time.time()
	csv_delta = t0 - tsWindow[startId]/1000.0
	def convert(csv_timestamp):
		return csv_timestamp/1000.0 + csv_delta
	
	def interpolator(timeWindow, valuesWindow):
		timestamps = list(convert(ts) for ts in timeWindow)
		values = list(valuesWindow)
		return CubicSpline(timestamps, values)
	
	acc_spline = interpolator(tsWindow, accWindow)
	csvHasNext = True
	while csvHasNext:
		now = time.time()
		
		while now > convert(tsWindow[slideId]) and csvHasNext:
			csvHasNext = slide(reader)
			acc_spline = interpolator(tsWindow, accWindow)
		
		if ACC_ENABLED:
			[ax, ay, az] = acc_spline(now)
			send(f"sensor set acceleration {ax}:{ay}:{az}")

		time.sleep(args.period/1000.0)

with open(args.csv_path, newline="") as f:
	reader = csv.reader(f)
	headers = next(reader)
	ts_idx = next(
		i for i, h in enumerate(headers)
		if "timestamp" in normalize(h)
	)
	acc_idx = find_indices(headers, ACC_ALIASES)
	gyr_idx = find_indices(headers, GYR_ALIASES)
	mag_idx = find_indices(headers, MAG_ALIASES)
	ACC_ENABLED = False if any(i is None for i in acc_idx) else ACC_ENABLED
	GYRO_ENABLED = False if any(i is None for i in gyr_idx) else GYRO_ENABLED
	MAG_ENABLED = False if any(i is None for i in mag_idx) else MAG_ENABLED
	print(f"csv format: ts={ts_idx} acc={acc_idx} gyro={gyr_idx} mag={mag_idx}")
	
	for i in range(int(args.r)):
		if args.period:
			interpolation(reader, ts_idx, acc_idx, gyr_idx, mag_idx)
		else:
			exact(reader, ts_idx, acc_idx, gyr_idx, mag_idx)
		
		if(int(args.r) > 1):
			print(f"injection completed {i+1}/{args.r}")
			f.seek(0)
			next(reader)