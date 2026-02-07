import subprocess
import time

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
		#if out != "OK": print(out)