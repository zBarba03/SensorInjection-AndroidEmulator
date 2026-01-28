#!/usr/bin/env python3

import argparse
import numpy as np

parser = argparse.ArgumentParser()
#esempio> ./mock.py 
parser.add_argument("csv_path", help="path to CSV file")
parser.add_argument("-r", type=int, default="1", help="number of repetitions of the csv file")
parser.add_argument("--interp")
parser.add_argument("--period", type=float, default="10", help="milliseconds between injections (interp only)")
args = parser.parse_args()

G = 9.80665  # m/s^2

class MockAccelerometer:
	def __init__(self, n_forces=3, seed=0):
		rng = np.random.default_rng(seed)

		self.n = n_forces
		self.amps = rng.uniform(0.2, 1.0, size=(n_forces, 3))
		self.freqs = rng.uniform(0.1, 2.0, size=n_forces)
		self.phases = rng.uniform(0, 2*np.pi, size=(n_forces, 3))

	#accelerometer value at time t (seconds)
	def value(self, t):
		t = np.asarray(t)

		acc = np.zeros(t.shape + (3,))

		for k in range(self.n):
			omega = 2 * np.pi * self.freqs[k]
			acc += self.amps[k] * np.sin(omega * t[..., None] + self.phases[k])

		acc[..., 2] += G
		return acc