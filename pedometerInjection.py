#!/usr/bin/env python3
import subprocess
import time
from appium import webdriver
#from appium.webdriver.common.appiumby import AppiumBy
from appium.options.android import UiAutomator2Options
from selenium.webdriver.common.by import By
import argparse
import csv
import os

parser = argparse.ArgumentParser()
parser.add_argument("reps", default=1, help="how many times each file is tested")
parser.add_argument("csvFiles", nargs="+", help="path to CSV files")
args = parser.parse_args()

WAIT_AFTER_CLICK = 1 # seconds
steplabPath = "/home/zbarba/uni/tesi/repo/steplab.apk"
sensorcsvPath = "/home/zbarba/uni/tesi/repo/sensorcsv.apk"
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

'''
def click(driver, text):
	driver.find_element(
		By.ANDROID_UIAUTOMATOR,
		('new UiScrollable(new UiSelector().scrollable(true))'
		f'.scrollIntoView(new UiSelector().textContains("{text}"))')
	).click()
	time.sleep(WAIT_AFTER_CLICK)
'''

def click(driver, id):
	driver.find_element(By.ID, f"com.example.steplab:id/{id}").click()

# navigates to live testing with Peak + Butterworth configuration
def startForlani(driver):
	if(driver.current_activity == ".ui.main.MainActivity"):
		driver.wait_activity(".ui.main.MainActivity", timeout=10)
		click(driver, "enter_configuration")
	else:
		driver.wait_activity(".ui.test.LiveTesting", timeout=10)
		click(driver, "new_pedometer")
	driver.wait_activity(".ui.test.LiveTesting", timeout=10)
	#time.sleep(WAIT_AFTER_CLICK)
	click(driver, "recognition_peak")
	click(driver, "butterworth_filter")
	click(driver, "start_pedometer")

def readSteps(driver):
	return driver.find_element(
		By.ID,
		f"com.example.steplab:id/step_count"
	).text



if __name__ == "__main__":
	appium_proc = start_appium()

	app = steplabPath
	driver = createDriver(app)
	
	outputPath = "./pedometerSteps.csv"
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

			for i in range(int(args.reps)):
				startForlani(driver)
				try:
					subprocess.run(
						["python3", "inject.py", "-a", file],
						stdout=subprocess.DEVNULL,
						stderr=subprocess.PIPE,
						text=True,
						check=True
					)
				except Exception as e:
					print(f"Error from inject.py: {e}")
					exit(1)
				steps = readSteps(driver)
				writer.writerow([file.split("/")[-1], "exact", "Peak+Butterworth", int(steps)])
				print(f" - {steps} steps")

	driver.quit()
	appium_proc.terminate()