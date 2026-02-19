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
parser.add_argument("reps", default=1, help="how many times each config is tested")
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
	options.app_package = "com.example.sensorcsv"
	options.app_activity= ".MainActivity"
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

def click(driver, text):
	# try clicking 10 times every second
	for _ in range(10):
		try:
			driver.find_element(
				AppiumBy.ANDROID_UIAUTOMATOR,
				'new UiScrollable(new UiSelector().scrollable(true))'
				f'.scrollIntoView(new UiSelector().textContains("{text}"))'
			)
			driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().textContains("{text}")').click()
			return
		except Exception as e:
			print(e)
			time.sleep(1.0)
	print(f"Error: Button {text} not found")
	quitAll(1)

def startReina(driver, magnitude, frequency, delay):
	click(driver, magnitude)
	click(driver, f"{frequency}Hz" if frequency != "0" else "maxHz")
	click(driver, delay)
	click(driver, "Start Recording")

def stopReina(driver):
	click(driver, "Stop and Save")

if __name__ == "__main__":
	appium_proc = start_appium()

	driver = createDriver(sensorcsvPath)
	
	click(driver, "Injection")

	for i in range(int(args.reps)):
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
	quitAll(0)