#!/home/zbarba/uni/tesi/repo/.venv/bin/python3
# Appium and selenium are installed in a virtual enviroment
import subprocess
from appium import webdriver # type: ignore
from appium.webdriver.common.appiumby import AppiumBy # type: ignore
from appium.options.android import UiAutomator2Options # type: ignore
from selenium.webdriver.common.by import By # type: ignore
import argparse
import csv
import os
from collections import defaultdict

parser = argparse.ArgumentParser()
parser.add_argument("app", choices=("steplab", "sensorcsv"), help="which app to test")
parser.add_argument("reps", type=int, default=1, help="how many times each config or file is tested")
parser.add_argument("csvFiles", nargs="*", help="path to real recordings of walks")
args = parser.parse_args()

appiumServerURL = 'http://localhost:4723'
driver = None
appium_proc = None
dirPath = "/home/zbarba/uni/tesi/"

# StepLab
steplabPath = dirPath+"repo/steplab.apk"
steplabPackage = "com.example.steplab"
steplabActivity = ".ui.main.MainActivity"
INTERP_ALGS = ["interp", "pchip"]
INTERP_FRQS = ["50", "100", "200"]
INTERPS = ["exact"] + [f"{alg}-{fr}" for alg in INTERP_ALGS for fr in INTERP_FRQS]
SAMPLINGS = ["50", "max"] # capped at 50 for interpolations at 50hz
ALGORITHMS = [("Peak","Butterworth"), # MAE 6-7 (Forlani)
			  ("Intersection", "LowPass+2%")] # MAE 30
REPETITIONS = 5
OUTPUT = dirPath+"pedometerSteps.csv"

# SensorCSV
sensorcsvPath = dirPath+"repo/sensorcsv.apk"
sensorcsvPackage = "com.example.sensorcsv"
sensorcsvActivity = ".MainActivity"
MAGNITUDES = ["Lower", "Normal", "Higher"]
FREQUENCIES = ["50", "100", "200", "500", "1000", "0"]
DELAYS = ["Game", "Fastest"]
ITERATIONS = 20

# -------- Automation --------

def start_appium():
	print("Starting Appium server... ", end="", flush=True)
	proc = subprocess.Popen(
		["appium"],
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		text=True
	)

	marker = "You can provide the following URL"

	for line in proc.stdout:
		if marker in line:
			print("Done")
			return proc
	print("failed")
	print(proc.stderr.read())
	exit(1)

def createDriver(app):
	if(app == "steplab"):
		apk = steplabPath
		package = steplabPackage
		activity = steplabActivity
	elif(app == "sensorcsv"):
		apk = sensorcsvPath
		package = sensorcsvPackage
		activity= sensorcsvActivity

	print(f"Launching {package}... ", end="", flush=True)
	options = UiAutomator2Options()
	options.platform_name = "Android"
	options.automation_name = "UiAutomator2"
	options.device_name = "Android Emulator"
	options.app = apk
	options.app_package = package
	options.app_activity= activity
	options.auto_grant_permissions = True
	options.language = "en"
	options.locale = "US"

	driver = webdriver.Remote(appiumServerURL, options=options)
	print("Done")
	return driver

def quitAll(val=0):
	print(" -- Testing completed --")
	driver.quit()
	appium_proc.terminate()
	exit(val)

def clickId(driver, id):
	driver.find_element(
		AppiumBy.ANDROID_UIAUTOMATOR,
		'new UiScrollable(new UiSelector().scrollable(true))'
		f'.scrollIntoView(new UiSelector().resourceId("com.example.steplab:id/{id}"))'
	)
	driver.find_element(AppiumBy.ID, f"com.example.steplab:id/{id}").click()

def clickText(driver, text):
	driver.find_element(
		AppiumBy.ANDROID_UIAUTOMATOR,
		'new UiScrollable(new UiSelector().scrollable(true))'
		f'.scrollIntoView(new UiSelector().textContains("{text}"))'
	)
	driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().textContains("{text}")').click()

def click(driver, txt=None, id=None):
	# try clicking 10 times
	for _ in range(10):
		try:
			if id is not None:
				clickId(driver, id)
			elif txt is not None:
				clickText(driver, txt)
			return
		except Exception as e:
			print(e)
			#time.sleep(0.5)
	print(f"Error: Text {txt} or id {id} not found")
	quitAll(1)

# -------- StepLab --------

def readSteps(driver):
	# reads steps of steplab live testing activity
	try:
		return driver.find_element(
			By.ID,
			f"com.example.steplab:id/step_count"
		).text
	except Exception as e:
		print(f"Error reading steps: {e}")
		quitAll(1)

def startForlaniLive(driver, algorithm="Peak", filter="Butterworth", sampling = "max"):
	# starts live testing with alg+filter configuration
	if(driver.current_activity == ".ui.main.MainActivity"):
		click(driver, id = "enter_configuration")
	else:
		click(driver, id = "new_pedometer")

	if sampling == "50":
		click(driver, id = "sampling_fifty")
	else:
		click(driver, id = "sampling_max")	

	match algorithm:
		case "Peak":
			click(driver, id = "recognition_peak")
		case "Intersection":
			click(driver, id = "recognition_intersection")
		case "TimeFiltering":
			click(driver, id = "time_filtering_alg")
		case _:
			print(f"No algorithm {algorithm}")

	match filter:
		case "Butterworth":
			click(driver, id = "butterworth_filter")
		case "LowPass+10Hz":
			click(driver, id = "filter_low_pass")
			click(driver, id = "cutoff_ten")
		case "LowPass+2%":
			click(driver, id = "filter_low_pass")
			click(driver, id = "cutoff_divided_fifty")
		case _:
			print(f"No filter {filter}")

	click(driver, id = "start_pedometer")

def exactInjection(file):
	try:
		subprocess.run(
			["python3", dirPath+"repo/inject.py", "-a", file],
			stdout=subprocess.DEVNULL,
			stderr=subprocess.PIPE,
			text=True,
			check=True
		)
	except Exception as e:
		print(f"Error from inject.py: {e}")
		exit(1)

def interpInjection(file, frequency, model="cubic"):
	try:
		subprocess.run(
			["python3", dirPath+"repo/interp.py", file, f"{frequency}", model],
			stdout=subprocess.DEVNULL,
			stderr=subprocess.PIPE,
			text=True,
			check=True
		)
	except Exception as e:
		print(f"Error from interp.py: {e}")
		exit(1)

def countProgress(realFiles):
	alreadyTested = defaultdict(int)

	if os.path.exists(OUTPUT):
		with open(OUTPUT, "r", newline="") as f:
			reader = csv.reader(f)
			for row in reader:
				file, mode, sampling, alg, steps = row
				if (any(file == os.path.basename(rf) for rf in realFiles) and
					any(mode == m for m in INTERPS) and
					any(sampling == m for m in SAMPLINGS) and
					any(alg == f"{a}+{filt}" for a, filt in ALGORITHMS)):
					alreadyTested[(file, mode, alg)] += 1

	# number capped at the repetitions we're interested in achieving
	for test in alreadyTested:
		if alreadyTested[test] >= REPETITIONS:
			alreadyTested[test] = REPETITIONS

	return alreadyTested

def testPedometer(driver, realFiles, action="live"):
	alreadyTested = countProgress(realFiles)
	tested = sum(alreadyTested.values())
	total = len(realFiles) * len(ALGORITHMS) * REPETITIONS * ((len(INTERPS) * len(SAMPLINGS)) - len(INTERP_ALGS)) # sampling cannot be max for interplations at 50
	print(f"Already tested: {tested} / {total}")

	seconds = 38 * (total - tested)
	hours = seconds // 3600
	mins = (seconds % 3600) // 60
	print(f"Roughly estimated time: {hours}h {mins}m")

	startInjection = input("Are you sure you can start this session? (y/n)")
	if startInjection.lower() != "y":
		quitAll(0)

	wasCreated = not os.path.exists(OUTPUT)
	with open(OUTPUT, "a", newline="") as f:
		writer = csv.writer(f)
		if wasCreated:
			writer.writerow(["file", "mode", "sampling", "algorithm", "steps"])

		for path in realFiles:
			print(f"file: {os.path.basename(path)}")
			for mode in INTERPS:
				# injection frequency
				for sampling in SAMPLINGS:

					if(sampling == "max" and mode.split("-")[1] == "50"):
						continue

					print(f"-mode: {mode} -> {sampling} sampling")
					for alg, filt in ALGORITHMS:
						print(f"- -algorithm: {alg}+{filt}")

						start = alreadyTested[(os.path.basename(path), mode, f"{alg}+{filt}")]
						for i in range(start, REPETITIONS):
							if action == "live":
								startForlaniLive(driver, alg, filt, sampling)
							elif action == "register":
								# TODO can't change sampling in register
								startForlaniRegister(driver, sampling)
							else:
								print(f"Unknown steplab action {action}")
								quitAll(1)

							if mode == "exact":
								exactInjection(path)
							else:
								interpInjection(path, mode.split("-")[1], model="cubic" if "cubic" in mode else "pchip")
							
							if action == "live":
								steps = readSteps(driver)
							else:
								steps = "0"
							
							writer.writerow([os.path.basename(path), mode, sampling, f"{alg}+{filt}", int(steps)])
							print(f"   | {steps} steps")

# -------- SensorCSV --------

def startReina(driver, magnitude, frequency, delay):
	click(driver, txt = magnitude)
	click(driver, txt = f"{frequency}Hz" if frequency != "0" else "maxHz")
	click(driver, txt = delay)
	click(driver, txt = "Start Recording")

def stopReina(driver):
	click(driver, txt = "Stop and Save")

def testMockInjection(driver):
	click(driver, txt = "Injection")
	for i in range(ITERATIONS):
		for magnitude in MAGNITUDES:
			for frequency in FREQUENCIES:
				for delay in DELAYS:
					print(f"- {magnitude}_{frequency}_{delay} {i}")
					startReina(driver, magnitude, frequency, delay)
					try:
						subprocess.run(
							["python3", dirPath+"repo/mock.py", magnitude, frequency, delay],
							stdout=subprocess.DEVNULL,
							stderr=subprocess.STDOUT,
							text=True,
							check=True
						)
					except Exception as e:
						print(f"Error from mock.py: {e}")
						exit(1)
					stopReina(driver)

# -------- Main --------

if __name__ == "__main__":
	appium_proc = start_appium()
	driver = createDriver(args.app.split("_")[0])
	
	if(args.app == "steplab"):
		testLivePedometer(driver, args.csvFiles)
	elif(args.app == "steplab_register"):
		testStaticPedometer(driver, args.csvFiles)
	elif(args.app == "sensorcsv"):
		testMockInjection(driver)

	quitAll(0)