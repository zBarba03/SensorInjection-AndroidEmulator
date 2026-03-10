#!/home/zbarba/uni/tesi/repo/.venv/bin/python3
# in my case Appium and selenium are installed in a virtual enviroment

import subprocess
from appium import webdriver
from appium.webdriver.common.appiumby import AppiumBy
from appium.options.android import UiAutomator2Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import InvalidSessionIdException
import argparse
import csv
import os
from collections import defaultdict
import time
import glob

# TODO >$ testInjection.py ./[app].apk [fun]
parser = argparse.ArgumentParser()
parser.add_argument("app", help="which app to test")
#parser.add_argument("csvFiles", nargs="*", help="path to real recordings of walks")
args = parser.parse_args()

appiumServerURL = 'http://localhost:4723'
driver = None
appium_proc = None
dirPath = "/home/zbarba/uni/tesi/"
walksPath = dirPath + "fulldata/*.csv"
interpPath = dirPath + "interp/*.csv"
reinaWalksPath = dirPath + "fulldata/Walk*.csv"
reinaRunsPath = dirPath + "fulldata/Run*.csv"

# StepLab live
INTERP_ALGS = ["cubic"] #, "pchip"
INTERP_FRQS = ["50"] #, "100", "200"
INTERPS = ["exact"] + [f"{alg}-{fr}" for alg in INTERP_ALGS for fr in INTERP_FRQS]
SAMPLINGS = ["50"] #, "max" # capped at 50 for interpolations at 50hz
ALGORITHMS = [("Peak","Butterworth")] # MAE 6-7 (Forlani)
# ("Intersection", "LowPass+2%") # MAE 30
REPETITIONS = 4
OUTPUT_LIVE = dirPath+"pedometerSteps3.csv" # interp -> inject
OUTPUT_LIVE2 = dirPath+"pedometerExactInterp.csv" # interp -> exact inject
OUTPUT_LIVE0 = dirPath+"pedometerExact.csv" # (exact ->) inject
OUTPUT_REGISTER = dirPath+"pedometerRegister.csv" # interp -> register inject -> static
OUTPUT_MAX = dirPath+"pedometerMaxFrequency.csv"
alreadyTested = defaultdict(int)
# StepLab static
OUTPUT_STATIC = dirPath+"verificationResults.csv"
alreadyVerified = set()

# SensorCSV
MAGNITUDES = ["Lower", "Normal", "Higher"]
FREQUENCIES = ["50", "100", "200", "500", "1000", "0"]
DELAYS = ["Game", "Fastest"]
ITERATIONS = 20

# -------- Automation --------

def start_appium():
	# Lancia il server appium e ne ritorna il subprocess
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

def createDriver():
	global driver
	if(args.app.startswith("steplab")):
		apk = dirPath+"repo/steplab.apk"
		package = "com.example.steplab"
		activity = ".ui.main.MainActivity"
	elif(args.app.startswith("sensorcsv")):
		apk = dirPath+"repo/sensorcsv.apk"
		package = "com.example.sensorcsv"
		activity= ".MainActivity"

	print(f"Launching {package}... ", end="", flush=True)
	options = UiAutomator2Options()
	options.platform_name = "Android"
	options.automation_name = "UiAutomator2"
	options.device_name = "Android Emulator"
	options.app = apk
	#options.app_package = package
	#options.app_activity= activity
	options.auto_grant_permissions = True
	options.language = "en"
	options.locale = "US"

	driver = webdriver.Remote(appiumServerURL, options=options)
	print("Done")

# This function restarts the application safely
# Can be used in the tests whenever an Exception occurs
# if you wish to continue the execution without user intervention
def resetDriver():
	global driver
	print("Driver Reset")
	try:
		driver.quit()
	except InvalidSessionIdException:
		pass
	finally:
		createDriver()

def quitAll(val=0):
	if val==0:
		print(" -- Testing completed --")
		driver.quit()
	else:
		print(" -- Terminated with Error --")
	appium_proc.terminate()
	exit(val)

def click(text=None, id=None, icon=None, scroll = True):
	# try clicking 5 times
	for i in range(5):
		try:
			if id is not None:
				if scroll:
					driver.find_element(
						AppiumBy.ANDROID_UIAUTOMATOR,
						'new UiScrollable(new UiSelector().scrollable(true))'
						f'.scrollIntoView(new UiSelector().resourceId("com.example.steplab:id/{id}"))'
					)
				driver.find_element(AppiumBy.ID, f"com.example.steplab:id/{id}").click()
			elif text is not None:
				if scroll:
					driver.find_element(
						AppiumBy.ANDROID_UIAUTOMATOR,
						'new UiScrollable(new UiSelector().scrollable(true))'
						f'.scrollIntoView(new UiSelector().textContains("{text}"))'
					)
				driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().textContains("{text}")').click()
			elif icon is not None:
				if scroll:
					driver.find_element(
						AppiumBy.ANDROID_UIAUTOMATOR,
						'new UiScrollable(new UiSelector().scrollable(true))'
						f'.scrollIntoView(new UiSelector().description({icon}))'
					)
				driver.find_element(AppiumBy.ACCESSIBILITY_ID, f"{icon}").click()
			return
		except Exception as e:
			if i>1:
				print("Struggling to find element")
			if not scroll: # otherwise the driver trying to scroll makes it wait
				time.sleep(1.0)
	print(f"Error: Text {text} or id {id} not found")
	quitAll(1)

# waits until the given argument appears on screen
def waitUntil(text=None, id=None, icon=None):
	try:
		if text is not None:
			WebDriverWait(driver, 30).until( EC.presence_of_element_located(
				(AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().textContains("{text}")')
			))
		elif id is not None:
			WebDriverWait(driver, 30).until( EC.presence_of_element_located(
				(AppiumBy.ID, f"com.example.steplab:id/{id}")
			))
		elif icon is not None:
			WebDriverWait(driver, 30).until( EC.presence_of_element_located(
				(AppiumBy.ACCESSIBILITY_ID, f"{icon}")
			))
	except TimeoutException:
		print(f"wait timeout for text={text} id={id}")

def read(id):
	try:
		return driver.find_element(
			AppiumBy.ID,
			f"com.example.steplab:id/{id}"
		).text
	except InvalidSessionIdException:
		print(f"Error reading {id}")
		raise

# -------- StepLab Live Testing --------

def selectConfiguration(algorithm="Peak", filter="Butterworth"):
	match algorithm:
		case "Peak":
			click(id = "recognition_peak")
		case "Intersection":
			click(id = "recognition_intersection")
		case "TimeFiltering":
			click(id = "time_filtering_alg")
		case _:
			print(f"No algorithm {algorithm}")
			quitAll(0)

	match filter:
		case "Butterworth":
			click(id = "butterworth_filter")
		case "LowPass+10Hz":
			click(id = "filter_low_pass")
			click(id = "cutoff_ten")
		case "LowPass+2%":
			click(id = "filter_low_pass")
			click(id = "cutoff_divided_fifty")
		case _:
			print(f"No filter {filter}")
			quitAll(0)

def startForlaniLive(algorithm="Peak", filter="Butterworth", sampling = "max"):
	# starts live testing with alg+filter configuration
	if(driver.current_activity == ".ui.main.MainActivity"):
		waitUntil(id="enter_configuration")
		click(id="enter_configuration")
	else:
		waitUntil(id="new_pedometer")
		click(id="new_pedometer")

	if sampling == "50":
		click(id="sampling_fifty")
	else:
		click(id="sampling_max")

	selectConfiguration(algorithm, filter)

	click(id="start_pedometer")

def exactInjection(path):
	try:
		subprocess.run(
			[dirPath+"repo/inject.py", "-a", path],
			stdout=subprocess.DEVNULL,
			stderr=subprocess.PIPE,
			text=True,
			check=True
		)
	except Exception as e:
		print(f"Error from inject.py: {e}")
		print(f"{dirPath}repo/inject.py -a {path}")
		quitAll(1)

def interpInjection(path, frequency, model="cubic"):
	try:
		subprocess.run(
			[dirPath+"repo/interp.py", path, f"{frequency}", model],
			stdout=subprocess.DEVNULL,
			stderr=subprocess.PIPE,
			text=True,
			check=True
		)
	except Exception as e:
		print(f"Error from interp.py: {e}")
		print(f"{dirPath}repo/interp.py {path} {frequency} {model}")
		quitAll(1)
	driver.orientation = "PORTRAIT"

def liveTests(paths, output=OUTPUT_LIVE, interps=INTERPS, samplings=SAMPLINGS, algorithms=ALGORITHMS, repetitions=REPETITIONS):
	countProgressLive(paths, output, interps, samplings, algorithms, repetitions)

	wasCreated = not os.path.exists(output)
	with open(output, "a", newline="") as f:
		writer = csv.writer(f)
		if wasCreated:
			writer.writerow(["file", "mode", "sampling", "algorithm", "steps"])

		for path in paths:
			# app is killed by android while these files are injected, probably because they're too long
			#if ("i_1759165519322_BABY_STEPS_POCKET_23_MALE_OPPO_CPH2219.csv" in path or
			#	"i_1759165821155_IRREGULAR_STEPS_POCKET_22_MALE_samsung_SM-G770F.csv" in path or
			#	"i_1758718532245_UPHILL_WALKING_SHOULDER_21_MALE_Xiaomi_M2003J15SC.csv" in path or
			#	"i_1759162921009_PLAIN_WALKING_HAND_55_FEMALE_Xiaomi_2109119DG.csv" in path):
			#	continue
			#print(f"file: {os.path.basename(path)}")
			for mode in interps:
				# injection frequency
				for sampling in samplings:
					#if("50" in mode and sampling == "max"):
					#	continue

					#print(f"-mode: {mode} -> {sampling} sampling")
					for alg, filt in algorithms:
						#print(f"- -algorithm: {alg}+{filt}")

						start = alreadyTested[(os.path.basename(path), mode, sampling, f"{alg}+{filt}")]
						for i in range(start, repetitions):
							try:
								startForlaniLive(alg, filt, sampling)

								if mode == "exact":
									exactInjection(path)
								else:
									interpInjection(path, mode.split("-")[1], model="cubic" if "cubic" in mode else "pchip")
								steps = read("step_count")
							except InvalidSessionIdException:
								print(f"failed injection of {os.path.basename(path)} {mode} -> {sampling} {alg}+{filt} {i}")
								resetDriver()
								break
							else:
								print(f" [{steps}]", end="", flush=True)
								#print(f"   | {steps} steps")
								writer.writerow([os.path.basename(path), mode, sampling, f"{alg}+{filt}", int(steps)])
								#alreadyTested[(os.path.basename(path), mode, sampling, f"{alg}+{filt}")] += 1

def registerTests(paths, output, interps=INTERPS, samplings=SAMPLINGS, algorithms=ALGORITHMS, repetitions=REPETITIONS):
	countProgressLive(paths, output, interps, samplings, algorithms, repetitions)

	wasCreated = not os.path.exists(output)
	with open(output, "a", newline="") as f:
		writer = csv.writer(f)
		if wasCreated:
			writer.writerow(["file", "mode", "sampling", "algorithm", "steps"])

		for path in paths:
			#print(f"file: {os.path.basename(path)}")
			for mode in interps:
				for sampling in samplings:

					#print(f"-mode: {mode} -> {sampling} sampling")
					for alg, filt in algorithms:
						#print(f"- -algorithm: {alg}+{filt}")

						start = alreadyTested[(os.path.basename(path), mode, sampling, f"{alg}+{filt}")]
						for i in range(start, repetitions):
							try:
								waitUntil(id="register_new_test")
								click(id="register_new_test", scroll=False)
								waitUntil(id="new_test_button")
								click(id="new_test_button", scroll=False)

								if mode == "exact":
									exactInjection(path)
								else:
									interpInjection(path, mode.split("-")[1], model="cubic" if "cubic" in mode else "pchip")

								click(id="new_test_button", scroll=False)
								click(id="save_new_test", scroll=False)

								steps = staticTest()
								sendToDrive()
								#deleteTest()
							except InvalidSessionIdException:
								print(f"failed injection of {os.path.basename(path)} {mode} -> {sampling} {alg}+{filt} {i}")
								resetDriver()
								break
							else:
								print(f"{steps}] ", end="", flush=True)
								#print(f"   | {steps} steps")
								writer.writerow([os.path.basename(path), mode, sampling, f"{alg}+{filt}", int(steps)])
								#alreadyTested[(os.path.basename(path), mode, sampling, f"{alg}+{filt}")] += 1
			#resetDriver()

# --------- StepLab Static Testing --------

def importFromDrive(file):
	waitUntil(id="import_test")
	click(id="import_test", scroll=False)
	waitUntil("175")
	click("Drive")
	waitUntil("My Drive")
	click("My Drive")
	if file.startswith("i_"):
		click("InterpDataset")
	else:
		click("WalkDataset")
	waitUntil("175")

	# hardcoded way to make this function reliable
	# search for a unique substring but click on a longer substring
	searchName = file[:15] if file.startswith("17") or file.startswith("i_17") else file[:-4]
	visibleName = file[:20] if file.startswith("17") or file.startswith("i_17") else file

	waitUntil(icon="Search")
	click(icon="Search", scroll=False)
	driver.switch_to.active_element.send_keys(searchName)

	waitUntil(visibleName)
	click(text=visibleName)
	waitUntil("Import Complete")
	click("Ok", scroll = False)

def sendToDrive():
	waitUntil(id="send_test")
	click(id="send_test", scroll=False)
	waitUntil(id="selected")
	click(id="selected", scroll=False)
	waitUntil(id="send_test")
	click(id="send_test", scroll=False)
	waitUntil("CSV")
	click("CSV", scroll=False)
	click(id="btn_export", scroll=False)
	#waitUntil("Drive")
	#click("Drive", scroll=False)
	#waitUntil("Upload")
	#click(icon="Upload", scroll=False)
	waitUntil("registrations") # folder appearing as shortcut
	click("registrations", scroll=False)
	print("snt[", end="", flush=True)
	waitUntil(id="delete_button")
	click(id="delete_button", scroll = False)
	waitUntil("Yes")
	click("Yes", scroll = False)
	time.sleep(1)
	driver.back()

def deleteTest():
	waitUntil(id="send_test")
	click(id="send_test", scroll=False)
	waitUntil(id="delete_button")
	click(id="delete_button", scroll = False)
	waitUntil("Yes")
	click("Yes", scroll = False)
	time.sleep(1)
	driver.back()

def staticTest(alg="Peak", filt="Butterworth"):
	click(id="compare_configurations")
	selectConfiguration(alg, filt)
	click(id="add_configuration")
	click(id="start_comparison")
	click(id="select", scroll = False) #the blue arrow
	time.sleep(5) #waitUntil(id="steps") #
	steps = read("steps")
	driver.back()
	return int(steps)

def test_A(file):
	importFromDrive(file)
	steps = staticTest("Peak", "Butterworth")
	deleteTest()
	return steps

'''
# equivalente a iniezione Live
def test_B(path):
	waitUntil(id="register_new_test")
	click(id="register_new_test", scroll=False)
	waitUntil(id="new_test_button")
	click(id="new_test_button", scroll=False)
	interpInjection(path, 50, "cubic")
	click(id="new_test_button", scroll=False)
	click(id="save_new_test", scroll=False)
	steps = staticTest()
	deleteTest()
	return steps
'''

def staticTests(files):
	wasCreated = not os.path.exists(OUTPUT_STATIC)
	files = [path for path in files if os.path.basename(path) not in alreadyVerified]
	with open(OUTPUT_STATIC, "a", newline="") as f:
		writer = csv.writer(f)
		if wasCreated:
			writer.writerow(["file", "a", "a_interp"])

		for i, path in enumerate(files, start=1):
			if i%8==0:
				resetDriver()

			file = os.path.basename(path)
			interpFile = "i_" + file

			print(f"A  = ", end="", flush=True)

			a = test_A(file) # camminata importata

			print(f"{a} / A' = ", end="", flush=True)

			a_interp = test_A(interpFile) # interpolazione importata

			print(f"{a_interp}    A-A' =   {a-a_interp}")

			writer.writerow([file,a,a_interp])

# -------- SensorCSV --------

def startReina(magnitude, frequency, delay):
	click(magnitude)
	click(f"{frequency}Hz" if frequency != "0" else "maxHz")
	click(delay)
	click("Start Recording")

def stopReina():
	click("Stop and Save")

def testMockInjection():
	click("Injection")
	for i in range(ITERATIONS):
		for magnitude in MAGNITUDES:
			for frequency in FREQUENCIES:
				for delay in DELAYS:
					print(f"- {magnitude}_{frequency}_{delay} {i}")
					startReina(magnitude, frequency, delay)
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
					stopReina()

# -------- Main --------

def countProgressLive(realFiles, output=OUTPUT_LIVE, interps=INTERPS, samplings=SAMPLINGS, algorithms=ALGORITHMS, repetitions=REPETITIONS):
	global alreadyTested
	alreadyTested = defaultdict(int)
	if os.path.exists(output):
		with open(output, "r", newline="") as f:
			reader = csv.reader(f)
			for row in reader:
				file, mode, sampling, alg, steps = row
				if (any(file == os.path.basename(rf) for rf in realFiles) and
					any(mode == m for m in interps) and
					any(sampling == m for m in samplings) and
					any(alg == f"{a}+{filt}" for a, filt in algorithms)):
					alreadyTested[(file, mode, sampling, alg)] += 1
		# number capped at the repetitions we're interested in achieving
		for test in alreadyTested:
			if alreadyTested[test] >= repetitions:
				alreadyTested[test] = repetitions

	tested = sum(alreadyTested.values())
	total = len(realFiles) * len(algorithms) * repetitions * len(interps) * len(samplings)
	#if "50" in INTERP_FRQS and "max" in samplings: # sampling cannot be max for interplations at 50
	#	total -= len(realFiles) * len(ALGORITHMS) * REPETITIONS * len([alg for alg in INTERPS if "50" in alg])
	print(f"Already tested: {tested} / {total}")

	seconds = 38 * (total - tested)
	hours = seconds // 3600
	mins = (seconds % 3600) // 60
	print(f"Estimated time: {hours}h {mins}m")

def countProgressStatic(paths):
	if not os.path.exists(OUTPUT_STATIC):
		return
	with open(OUTPUT_STATIC, newline="") as f:
		reader = csv.reader(f)
		next(reader, None)
		for row in reader:
			if row:
				alreadyVerified.add(row[0])

	total = len(paths)
	tested = len(alreadyVerified)
	print(f"Already tested: {tested} / {total}")

	seconds = 90 * (total - tested)
	hours = seconds // 3600
	mins = (seconds % 3600) // 60
	print(f"Estimated time: {hours}h {mins}m")

	startInjection = input("Are you sure you can start this session? (y/n) ")
	if startInjection.lower() != "y": quit(0)

if __name__ == "__main__":

	if(args.app == "steplab_static"):
		countProgressStatic(glob.glob(walksPath))

	appium_proc = start_appium()
	createDriver()

	try:
		# ogni test è hard-coded.
		# sono presenti alcune funzioni generali in grado di semplificarne la codifica,
		# ma la gestione di molte eccezioni e il riavvio dell'applicazione dipende dai singoli test e applicazioni.
		if args.app == "steplab_live":
			print("######## REINA WALKS ########")
			liveTests(glob.glob(reinaWalksPath) + glob.glob(reinaRunsPath), OUTPUT_LIVE0, interps=['exact'], repetitions=20)
			liveTests(glob.glob(reinaWalksPath) + glob.glob(reinaRunsPath), OUTPUT_LIVE, interps=['cubic-50'], repetitions=20)
			print("######## FULL DATA 10 ########")
			liveTests(glob.glob(walksPath), OUTPUT_LIVE0, interps=['exact'], repetitions=10)
			liveTests(glob.glob(walksPath), OUTPUT_LIVE, interps=['cubic-50'], repetitions=10)
			print("\n\n\n######## FULL DATA COMPLETED ########")
		elif args.app == "steplab_register":
			registerTests(glob.glob(reinaWalksPath), OUTPUT_REGISTER, interps=['exact'], repetitions=5)
		elif args.app == "steplab_static":
			staticTests(glob.glob(walksPath))
		elif args.app == "sensorcsv":
			testMockInjection()
		quitAll(0)
	except:
		appium_proc.terminate()
		raise