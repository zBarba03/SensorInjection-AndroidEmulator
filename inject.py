#!/usr/bin/env python3

import csv
import subprocess
import time
import re
import argparse

parser = argparse.ArgumentParser()
#$> ./inject.py [-agm] path/to/file.csv [-r=1] [spline algorithm + time between injections in ms]
parser.add_argument("-a", action="store_true", help="enable accelerometer")
parser.add_argument("-g", action="store_true", help="enable gyroscope")
parser.add_argument("-m", action="store_true", help="enable magnetic field")
parser.add_argument("csv_path", help="path to CSV file")
parser.add_argument("-r", default="1", help="number of repetitions of the csv file")

args = parser.parse_args()

if not (args.a or args.g or args.m):
    ACC_ENABLED = GYRO_ENABLED = MAG_ENABLED = True
else:
    ACC_ENABLED = args.a
    GYRO_ENABLED = args.g
    MAG_ENABLED = args.m

EMULATOR_HOST = "localhost"
EMULATOR_PORT = 5554   # change if needed

# -------- column normalization --------
def normalize(col):
	return re.sub(r'[^a-z]', '', col.lower())

ACC_ALIASES = {"ax", "accelerometerx"}, \
			  {"ay", "accelerometery"}, \
			  {"az", "accelerometerz"}
GYR_ALIASES = {"gx", "gyroscopex"}, \
			  {"gy", "gyroscopey"}, \
			  {"gz", "gyroscopez"}
MAG_ALIASES = {"mx", "magnetometerx"}, \
			  {"my", "magnetometery"}, \
			  {"mz", "magnetometerz"}

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

# -------- emulator console --------
proc = subprocess.Popen(
	["nc", EMULATOR_HOST, str(EMULATOR_PORT)],
	stdin=subprocess.PIPE,
	stdout=subprocess.PIPE,
	stderr=subprocess.STDOUT,
	text=True,
	bufsize=1
)

def send(cmd):
	proc.stdin.write(cmd + "\n")
	proc.stdin.flush()
	out = proc.stdout.readline().strip()
	print(f"{time.time()}> {cmd}")
	if out != "OK":
		print(out)

def inject(row):
	if ACC_ENABLED and all(i is not None for i in acc_idx):
		ax, ay, az = (row[i] for i in acc_idx)
		send(f"sensor set acceleration {ax}:{ay}:{az}")

	if GYRO_ENABLED and all(i is not None for i in gyr_idx):
		gx, gy, gz = (row[i] for i in gyr_idx)
		send(f"sensor set gyroscope {gx}:{gy}:{gz}")

	if MAG_ENABLED and all(i is not None for i in mag_idx):
		mx, my, mz = (row[i] for i in mag_idx)
		send(f"sensor set magnetic-field {mx}:{my}:{mz}")

# -------- main --------
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

	print(f"idx: {ts_idx} {acc_idx} {gyr_idx} {mag_idx}")

	for i in range(int(args.r)):
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
			print("----")
			
			print(f"calculated timediff (ms) = {(target_real-now_real) *1000}")
			print(f"actual timediff (ms) =     {(time.monotonic()-now_real) *1000}")
			beforeInject = time.monotonic()
			inject(row)
			afterInject = time.monotonic()
			print(f"injection took {(afterInject-beforeInject)*1000} milliseconds")
		
		if(int(args.r) > 1):
			print(f"injection completed {i+1}/{args.r}")
			f.seek(0)
			next(reader)