#!/home/zbarba/uni/tesi/repo/.venv/bin/python3
# Appium and selenium are installed in a virtual enviroment
import subprocess
import time
from appium import webdriver
from appium.webdriver.common.appiumby import AppiumBy
from appium.options.android import UiAutomator2Options
from selenium.webdriver.common.by import By
import argparse
import csv
import os

parser = argparse.ArgumentParser()
parser.add_argument("app", choices=("steplab", "sensorcsv"), help="which app to test")
parser.add_argument("reps", type=int, default=1, help="how many times each config or file is tested")
parser.add_argument("csvFiles", nargs="+", help="path to real recordings of walks", required=False)
args = parser.parse_args()

appiumServerURL = 'http://localhost:4723'
dirPath = "/home/zbarba/uni/tesi/"

steplabPath = dirPath+"repo/steplab.apk"
steplabPackage = "com.example.steplab"
steplabActivity = ".ui.main.MainActivity"

sensorcsvPath = dirPath+"repo/sensorcsv.apk"
sensorcsvPackage = "com.example.sensorcsv"
sensorcsvActivity = ".MainActivity"

def start_appium():
	print("Starting Appium server... ", end="", flush=True)
	proc = subprocess.Popen(
		["appium"],
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		text=True
	)

	marker = "You can provide the following URLs in your client code to connect to this server:"

	for line in proc.stdout:
		if marker in line:
			print("Done")
			return proc
	print("failed")
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
	#options.app = dirPath + apk
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

def click(driver, id=None, txt=None):
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
			time.sleep(1.0)
	print(f"Error: Text {txt} or id {id} not found")
	quitAll(1)

# reads steps of steplab live testing activity
def readSteps(driver):
	try:
		return driver.find_element(
			By.ID,
			f"com.example.steplab:id/step_count"
		).text
	except Exception as e:
		print(f"Error reading steps: {e}")
		quitAll(1)

# starts live testing with alg+filter configuration
def startForlani(driver, algorithm="Peak", filter="Butterworth"):
	if(driver.current_activity == ".ui.main.MainActivity"):
		click(driver, id = "enter_configuration")
	else:
		click(driver, id = "new_pedometer")
	
	match algorithm:
		case "Peak":
			click(driver, id = "recognition_peak")
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

# tests files in real/ directory, with all alg+filter configurations, and writes results in pedometerSteps.csv
def testPedometer(driver, realFiles, outputFile, repetitions):
	wasCreated = not os.path.exists(outputFile)
	with open(outputFile, "a", newline="") as f:
		writer = csv.writer(f)
		# realFile path
		# mode of injection (exact,interp10ms,interp0ms)
		# algorithm (Peak+Butterworth...)
		# steps detected
		if wasCreated:
			writer.writerow(["file", "mode", "algorithm", "steps"])

		for file in realFiles:
			print(f"file> {file}")

			for alg in ["Peak", "TimeFiltering"]:
				for filt in ["Butterworth", "LowPass+10Hz", "LowPass+2%"]:
					print(f"- alg> {alg}+{filt}")

					for i in range(repetitions):
						startForlani(driver, algorithm=alg, filter=filt)
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
						steps = readSteps(driver)
						writer.writerow([file.split("/")[-1], "exact", f"{alg}+{filt}", int(steps)])
						print(f"| - {steps} steps")
	
def startReina(driver, magnitude, frequency, delay):
	click(driver, txt = magnitude)
	click(driver, txt = f"{frequency}Hz" if frequency != "0" else "maxHz")
	click(driver, txt = delay)
	click(driver, txt = "Start Recording")

def stopReina(driver):
	click(driver, txt = "Stop and Save")

def testMockInjection(driver, repetitions):
	click(driver, "Injection")
	for i in range(repetitions):
		for magnitude in ["Lower", "Normal", "Higher"]:
			for frequency in ["50", "100", "200", "500", "1000", "0"]:
				for delay in ["DELAY-GAME", "DELAY-FASTEST"]:
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

if __name__ == "__main__":
	appium_proc = start_appium()
	driver = createDriver(args.app)
	
	if(args.app == "steplab"):
		testPedometer(driver, args.csvFiles, dirPath+"repo/pedometerSteps.csv", args.reps)
	elif(args.app == "sensorcsv"):
		testMockInjection(driver, args.reps)

	quitAll(0)