#!/home/zbarba/uni/tesi/repo/.venv/bin/python3
# Appium and selenium are installed in a virtual enviroment
import subprocess
from appium import webdriver # type: ignore
from appium.webdriver.common.appiumby import AppiumBy # type: ignore
from appium.options.android import UiAutomator2Options # type: ignore
from selenium.webdriver.common.by import By # type: ignore
from selenium.webdriver.support.ui import WebDriverWait # type: ignore
from selenium.webdriver.support import expected_conditions as EC # type: ignore
import argparse
import csv
import os
from collections import defaultdict
import time
import glob

parser = argparse.ArgumentParser()
parser.add_argument("app", choices=("steplab", "steplab_verification", "sensorcsv"), help="which app to test")
#parser.add_argument("csvFiles", nargs="*", help="path to real recordings of walks")
args = parser.parse_args()

appiumServerURL = 'http://localhost:4723'
driver = None
appium_proc = None
dirPath = "/home/zbarba/uni/tesi/"
walksPath = dirPath + "fulldata/*"

# StepLab
INTERP_ALGS = ["cubic"] #, "pchip"
INTERP_FRQS = ["50"] #, "100", "200"
INTERPS = [f"{alg}-{fr}" for alg in INTERP_ALGS for fr in INTERP_FRQS] #["exact"] + 
SAMPLINGS = ["50"] #, "max" # capped at 50 for interpolations at 50hz
ALGORITHMS = [("Peak","Butterworth")] # MAE 6-7 (Forlani)
# ("Intersection", "LowPass+2%") # MAE 30
REPETITIONS = 5
OUTPUT = dirPath+"pedometerSteps3.csv"
alreadyTested = defaultdict(int)
OUTPUT_VERIFICATION = dirPath+"verificationResults.csv"
alreadyVerified = set()

# SensorCSV
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

def createDriver():
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
	return driver

def resetDriver():
	print("Driver Reset")
	if driver is not None:
		driver.quit()
	driver = createDriver()

def quitAll(val=0):
	if val==0:
		print(" -- Testing completed --")
	else:
		print(" -- Terminated with Error --")
	driver.quit()
	appium_proc.terminate()
	exit(val)

def clickId(id, scroll):
	if scroll:
		driver.find_element(
			AppiumBy.ANDROID_UIAUTOMATOR,
			'new UiScrollable(new UiSelector().scrollable(true))'
			f'.scrollIntoView(new UiSelector().resourceId("com.example.steplab:id/{id}"))'
		)
	driver.find_element(AppiumBy.ID, f"com.example.steplab:id/{id}").click()

def clickText(text, scroll):
	if scroll:
		driver.find_element(
			AppiumBy.ANDROID_UIAUTOMATOR,
			'new UiScrollable(new UiSelector().scrollable(true))'
			f'.scrollIntoView(new UiSelector().textContains("{text}"))'
		)
	driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().textContains("{text}")').click()

def clickIcon(icon, scroll):
	if scroll:
		driver.find_element(
			AppiumBy.ANDROID_UIAUTOMATOR,
			'new UiScrollable(new UiSelector().scrollable(true))'
			f'.scrollIntoView(new UiSelector().description({icon}))'
		)
	driver.find_element(AppiumBy.ACCESSIBILITY_ID, f"{icon}").click()

def click(text=None, id=None, icon=None, scroll = True):
	# try clicking 5 times
	for i in range(5):
		try:
			if id is not None:
				clickId(id, scroll)
			elif text is not None:
				clickText(text, scroll)
			elif icon is not None:
				clickIcon(icon, scroll)
			return
		except Exception as e:
			if i>1:
				print("Struggling to find element")
			if not scroll:
				time.sleep(1.0)
	print(f"Error: Text {text} or id {id} not found")
	quitAll(1)

def waitUntil(text=None, id=None, icon=None):
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

# -------- StepLab --------

def readSteps():
	# reads steps of steplab live testing activity
	try:
		return driver.find_element(
			By.ID,
			f"com.example.steplab:id/step_count"
		).text
	except Exception as e:
		print(f"Error reading steps: {e}")
		quitAll(1)

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
		click(id = "enter_configuration")
	else:
		click(id = "new_pedometer")

	if sampling == "50":
		click(id = "sampling_fifty")
	else:
		click(id = "sampling_max")

	selectConfiguration(algorithm, filter)

	click(id = "start_pedometer")

def exactInjection(file):
	try:
		subprocess.run(
			[dirPath+"repo/inject.py", "-a", file],
			stdout=subprocess.DEVNULL,
			stderr=subprocess.PIPE,
			text=True,
			check=True
		)
	except Exception as e:
		print(f"Error from inject.py: {e}")
		print(f"{dirPath}repo/inject.py -a {file}")
		exit(1)

def interpInjection(file, frequency, model="cubic"):
	try:
		subprocess.run(
			[dirPath+"repo/interp.py", dirPath+file, f"{frequency}", model],
			stdout=subprocess.DEVNULL,
			stderr=subprocess.PIPE,
			text=True,
			check=True
		)
	except Exception as e:
		print(f"Error from interp.py: {e}")
		print(f"{dirPath}repo/interp.py {dirPath}{file} {frequency} {model}")
		exit(1)

def testPedometer(realFiles):

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

					if("50" in mode and sampling == "max"):
						continue

					print(f"-mode: {mode} -> {sampling} sampling")
					for alg, filt in ALGORITHMS:
						print(f"- -algorithm: {alg}+{filt}")

						start = alreadyTested[(os.path.basename(path), mode, sampling, f"{alg}+{filt}")]
						for i in range(start, REPETITIONS):
							startForlaniLive(alg, filt, sampling)

							if mode == "exact":
								exactInjection(path)
							else:
								interpInjection(path, mode.split("-")[1], model="cubic" if "cubic" in mode else "pchip")
							
							steps = readSteps()
							
							writer.writerow([os.path.basename(path), mode, sampling, f"{alg}+{filt}", int(steps)])
							print(f"   | {steps} steps")

# --------- StepLab Verification --------

def importFromDrive(file):
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

	# searchName è piu corto di visibleName,
	# altrimenti clicchiamo sul testo appena scritto invece che nel file trovato
	# visibleName dev'essere ridotto perche i nomi troppo lunghi vengono troncati con "..."
	# tutto hardcoded

	searchName = file[:15] if file.startswith("17") or file.startswith("i_17") else file[:-3]
	visibleName = file[:20] if file.startswith("17") or file.startswith("i_17") else file

	waitUntil(icon="Search")
	#WebDriverWait(driver, 30).until(
	#	EC.presence_of_element_located((AppiumBy.ACCESSIBILITY_ID, "Search"))
	#)
	click(icon="Search", scroll=False)
	#driver.find_element(AppiumBy.ACCESSIBILITY_ID, "Search").click()
	driver.switch_to.active_element.send_keys(searchName)
	#driver.press_keycode(66)

	waitUntil(visibleName)
	click(text=visibleName)
	waitUntil("Import Complete")
	click("Ok", scroll = False)

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
	try:
		steps = driver.find_element(
			AppiumBy.ID,
			f"com.example.steplab:id/steps"
		).text
	except Exception as e:
		print(f"Error reading steps: {e}")
		quitAll(1)
	driver.back()
	return int(steps)

def test_A(file):
	importFromDrive(file)
	steps = staticTest("Peak", "Butterworth")
	deleteTest()
	return steps

'''
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

def fullTest(files):
	wasCreated = not os.path.exists(OUTPUT_VERIFICATION)
	files = [path for path in files if os.path.basename(path) not in alreadyVerified]
	with open(OUTPUT_VERIFICATION, "a", newline="") as f:
		writer = csv.writer(f)
		if wasCreated:
			writer.writerow(["file", "a", "a_interp"])

		for i, path in enumerate(files, start=1):
			#if i%5==0:
			#	resetDriver()
			file = os.path.basename(path)
			interpFile = "i_" + file

			print(f"A  = ", end="", flush=True)

			a = test_A(file) # camminata importata

			print(f"{a} / A' = ", end="", flush=True)

			a_interp = test_A(interpFile) # interpolazione importata

			print(f"{a_interp}    A-A' =   {a-a_interp}")

			writer.writerow([file,a,a_interp])

# A-A' differenza sostanziale dovuta a interpolazione
# A'-B differenza nulla dovuta a iniezione


'''
A  = file originale importato da drive -> test statico su Peak+Butterworth
A' = modello di interpolazione -> test statico su Peak+Butterworth
	interpolazione cubic-50, lettura statica
B  = file iniettato in registrazione -> test statico su Peak+Butterworth
	interpolazione cubic-50, lettura 50hz

cubic-50
sampling 50hz <== forlani_register modificato
Peak+Butterworth

camminata reale -> test statico
modello di interpolazione A
interpolazione iniettato in register B ->
'''

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

def countProgress(realFiles):
	if os.path.exists(OUTPUT):
		with open(OUTPUT, "r", newline="") as f:
			reader = csv.reader(f)
			for row in reader:
				file, mode, sampling, alg, steps = row
				if (any(file == os.path.basename(rf) for rf in realFiles) and
					any(mode == m for m in INTERPS) and
					any(sampling == m for m in SAMPLINGS) and
					any(alg == f"{a}+{filt}" for a, filt in ALGORITHMS)):
					alreadyTested[(file, mode, sampling, alg)] += 1
		# number capped at the repetitions we're interested in achieving
		for test in alreadyTested:
			if alreadyTested[test] >= REPETITIONS:
				alreadyTested[test] = REPETITIONS

	tested = sum(alreadyTested.values())
	total = len(realFiles) * len(ALGORITHMS) * REPETITIONS * len(INTERPS) * len(SAMPLINGS)
	#if "50" in INTERP_FRQS: # sampling cannot be max for interplations at 50
	#	total -= len(realFiles) * len(ALGORITHMS) * REPETITIONS * len([alg for alg in INTERPS if "50" in alg])
	print(f"Already tested: {tested} / {total}")

	seconds = 38 * (total - tested)
	hours = seconds // 3600
	mins = (seconds % 3600) // 60
	print(f"Estimated time: {hours}h {mins}m")

	startInjection = input("Are you sure you can start this session? (y/n) ")
	if startInjection.lower() != "y":
		quit(0)

def countProgressVerification():
	if not os.path.exists(OUTPUT_VERIFICATION):
		return
	with open(OUTPUT_VERIFICATION, newline="") as f:
		reader = csv.reader(f)
		next(reader, None)
		for row in reader:
			if row:
				alreadyVerified.add(row[0])

	total = len(glob.glob(dirPath + "fulldata/*"))
	tested = len(alreadyVerified)
	print(f"Already tested: {tested} / {total}")

	seconds = 75 * (total - tested)
	hours = seconds // 3600
	mins = (seconds % 3600) // 60
	print(f"Estimated time: {hours}h {mins}m")

	startInjection = input("Are you sure you can start this session? (y/n) ")
	if startInjection.lower() != "y":
		quit(0)

if __name__ == "__main__":
	if(args.app == "steplab"):
		countProgress(glob.glob(walksPath))
	elif(args.app == "steplab_verification"):
		countProgressVerification()
	
	appium_proc = start_appium()
	driver = createDriver()

	try:
		if(args.app == "steplab"):
			testPedometer(glob.glob(walksPath))
		elif(args.app == "steplab_verification"):
			fullTest(glob.glob(walksPath))
		elif(args.app == "sensorcsv"):
			testMockInjection()
		quitAll(0)
	except Exception:
		appium_proc.terminate()
		raise