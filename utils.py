import subprocess
import time
import numpy as np
from scipy.interpolate import CubicSpline, PchipInterpolator

######## -------- ANDROID EMULATOR -------- ########

EMULATOR_HOST = "localhost"
EMULATOR_PORT = 5554

proc = subprocess.Popen(
	["nc", EMULATOR_HOST, str(EMULATOR_PORT)],
	stdin=subprocess.PIPE,
	stdout=subprocess.PIPE,
	stderr=subprocess.STDOUT,
	text=True,
	bufsize=1
)

def send(cmd: str, verbose: bool = False):
	proc.stdin.write(cmd + "\n")
	proc.stdin.flush()
	if verbose:
		out = proc.stdout.readline().strip()
		print(f"{time.time():.3f}> {cmd}")
		if out != "OK": print(out)

######## -------- MOCK MODEL -------- ########

G = 9.80665  # m/s^2

class AccelerometerModel:
	def __init__(self, n_waves=5, seed=2, magnitude=(3.0, -2.0, 2.0)):
		rng = np.random.default_rng(seed)
		self.n = n_waves
		self.amps = rng.uniform(magnitude[1], magnitude[2], size=(n_waves, 3))
		self.freqs = rng.uniform(0.1, 8.0, size=n_waves)
		self.phases = rng.uniform(0, 2*np.pi, size=(n_waves, 3))
		
		self.amps[0] = magnitude[0]
		self.freqs[0] = 2.0
		self.phases[0] = 0

	def value(self, t):
		t = np.asarray(t)
		acc = np.zeros(t.shape + (3,))
		for k in range(self.n):
			omega = 2 * np.pi * self.freqs[k]
			acc += self.amps[k] * np.sin(omega * t[..., None] + self.phases[k])
		
		acc[..., 2] += G
		return acc

def getModel(magnitude: str):
	if (magnitude=="Lower"):
		return AccelerometerModel(magnitude=(2.5,-2.0,2.0))
	if (magnitude=="Normal"):
		return AccelerometerModel(magnitude=(4.5, -3.5, 3.5))
	if (magnitude=="Higher"):
		return AccelerometerModel(magnitude=(10.0, -6.0, 6.0))
	else:
		raise ValueError("unknown magnitude")

######## -------- INTERPOLATION -------- ########

S2NS = 1000000000

class InterpolationModel:
	def __init__(self, file, kind="cubic"):
		data = np.loadtxt(file, delimiter=",", skiprows=1)

		# first column is in milliseconds since epoch
		# convert to nanoseconds since start
		timestamps = (data[:,0] - data[:,0].min()) * 1000000
		
		ax = data[:, 1]
		ay = data[:, 2]
		az = data[:, 3]
		
		# fourth column is nanoseconds.
		# not present in recorded "real" files as it was added later
		self.hasNano = False
		try:
			timestamps = data[:,4] - data[:,4].min()
			self.hasNano = True
			print("WARNING: using nanosecond precision")
		except:	pass
		
		if not np.all(np.diff(timestamps) > 0):
			raise ValueError("Timestamps not monotonic??")

		self.t_max = timestamps[-1]
		if(kind == "pchip"):
			self.spline_ax = PchipInterpolator(timestamps, ax)
			self.spline_ay = PchipInterpolator(timestamps, ay)
			self.spline_az = PchipInterpolator(timestamps, az)
		else: # cubic
			self.spline_ax = CubicSpline(timestamps, ax, bc_type="natural")
			self.spline_ay = CubicSpline(timestamps, ay, bc_type="natural")
			self.spline_az = CubicSpline(timestamps, az, bc_type="natural")

	def value_ns(self, t):
		if t < 0 or t > self.t_max:
			raise ValueError(f"interpolation out of bounds, received {t/S2NS}s, expected in range [0, {self.t_max/S2NS}s]")

		return (
			float(self.spline_ax(t)),
			float(self.spline_ay(t)),
			float(self.spline_az(t)),
		)

	def duration_ns(self):
		return self.t_max