import numpy as np

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