#!/home/zbarba/uni/tesi/repo/.venv/bin/python3
# Appium and selenium are installed in a virtual enviroment.
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
parser.add_argument("reps", default=1, help="how many times each file is tested")
parser.add_argument("csvFiles", nargs="+", help="path to CSV files")
args = parser.parse_args()

dirPath = "/home/zbarba/uni/tesi/"
steplabPath = dirPath+"repo/steplab.apk"
sensorcsvPath = dirPath+"repo/sensorcsv.apk"
appiumServerURL = 'http://localhost:4723'

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

def createDriver(apk_path):
	print(f"Starting app {apk_path}... ", end="", flush=True)
	options = UiAutomator2Options()
	options.platform_name = "Android"
	options.automation_name = "UiAutomator2"
	options.device_name = "Android Emulator"
	#options.app = apk_path
	options.app_package = "com.example.steplab"
	options.app_activity= ".ui.main.MainActivity"
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

def click(driver, id):
	# try clicking 10 times every second
	for _ in range(10):
		try:
			driver.find_element(
				AppiumBy.ANDROID_UIAUTOMATOR,
				'new UiScrollable(new UiSelector().scrollable(true))'
				f'.scrollIntoView(new UiSelector().resourceId("com.example.steplab:id/{id}"))'
			)
			driver.find_element(AppiumBy.ID, f"com.example.steplab:id/{id}").click()
			return
		except NoSuchElementException:
			time.sleep(1.0)
	print(f"Error: Button {id} not found")
	quitAll(1)

# starts live testing with alg configuration
def startForlani(driver, algorithm="Peak", filter="Butterworth"):
	if(driver.current_activity == ".ui.main.MainActivity"):
		click(driver, "enter_configuration")
	else:
		click(driver, "new_pedometer")
	
	match algorithm:
		case "Peak":
			click(driver, "recognition_peak")
		case "TimeFiltering":
			click(driver, "time_filtering_alg")
		case _:
			print(f"No algorithm {algorithm}")

	match filter:
		case "Butterworth":
			click(driver, "butterworth_filter")
		case "LowPass+10Hz":
			click(driver, "filter_low_pass")
			click(driver, "cutoff_ten")
		case "LowPass+2%":
			click(driver, "filter_low_pass")
			click(driver, "cutoff_divided_fifty")
		case _:
			print(f"No filter {filter}")

	click(driver, "start_pedometer")

def readSteps(driver):
	try:
		return driver.find_element(
			By.ID,
			f"com.example.steplab:id/step_count"
		).text
	except Exception as e:
		print(f"Error reading steps: {e}")
		quitAll(1)

if __name__ == "__main__":
	appium_proc = start_appium()

	app = steplabPath
	driver = createDriver(app)
	
	outputPath = dirPath+"repo/pedometerSteps.csv"
	wasCreated = not os.path.exists(outputPath)
	
	with open(outputPath, "a", newline="") as f:
		writer = csv.writer(f)
		# file path
		# mode of injection (exact,interp10ms,interp0ms)
		# algorithm (Peak+Butterworth...)
		# steps detected by forlani
		if wasCreated:
			writer.writerow(["file", "mode", "algorithm", "steps"])

		for file in args.csvFiles:
			print(f"file> {file}")

			for alg in ["Peak", "TimeFiltering"]:
				for filt in ["Butterworth", "LowPass+10Hz", "LowPass+2%"]:
					
					#tmp, already recorded this
					if(alg == "Peak" and filt == "Butterworth"):
						continue
					
					print(f" by {alg}+{filt}")
					for i in range(int(args.reps)):
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
						print(f"    - {steps} steps")
	
	quitAll(0)