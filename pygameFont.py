#!/usr/bin/env python

import pygame
import os
import datetime, time, logging
import RPi.GPIO as GPIO
import urllib, json, atexit
import xml.etree.ElementTree as ET
import random
from w1thermsensor import W1ThermSensor

def make_font(fonts, size):
	available = pygame.font.get_fonts()
	# get_fonts() returns a list of lowercase spaceless font names
	choices = map(lambda x:x.lower().replace(' ', ''), fonts)
	for choice in choices:
		if choice in available:
			return pygame.font.SysFont(choice, size)
	return pygame.font.Font(None, size)
	
_cached_fonts = {}
def get_font(font_preferences, size):
	global _cached_fonts
	key = str(font_preferences) + '|' + str(size)
	font = _cached_fonts.get(key, None)
	if font == None:
		font = make_font(font_preferences, size)
		_cached_fonts[key] = font
	return font

_cached_text = {}
def create_text(text, fonts, size, color):
	global _cached_text
	key = '|'.join(map(str, (fonts, size, color, text)))
	image = _cached_text.get(key, None)
	if image == None:
		font = get_font(fonts, size)
		image = font.render(text, True, color)
		_cached_text[key] = image
	return image
	
def my_callback(channel):  
	#global time_stamp	   # put in to debounce  
	global targetTemp
	#global buttonPressed
	#if (buttonPressed == 0):
	#	buttonPressed = GPIO.input(channel)
	#else:
	if(channel == switchUp):
		targetTemp = targetTemp +1
	if(channel == switchDown):
		targetTemp = targetTemp -1
	#print targetTemp
	#	buttonPressed = GPIO.input(channel)
	#print buttonPressed

def turnHeating(action):
	global heatingStatus
	if( action == "on"):
		if (heatingStatus == 0):
			#turn the heating on, this consists of the pump and the boiler
			#print "Function Turning Heating On!"
			heatingStatus = 1		
			
	else:
		if ( heatingStatus == 1):
			#Turn the heating off
			#print "Funtion Turning Heating Off"
			heatingStatus = 0

def checkRiverLevel():
	GPIO.output(statusLed, 1)
	response = urllib.urlopen(stationUrl)
	data = json.load(response)
	riverLevel = str(data["items"]["measures"]["latestReading"]["dateTime"]) +","+str(data["items"]["measures"]["latestReading"]["value"])
	GPIO.output(statusLed, 0)
	return riverLevel

def checkFloodAlert():
	GPIO.output(statusLed, 1)
	response = urllib.urlopen(floodUrl)
	data = json.load(response)
	GPIO.output(statusLed, 0)
	
	#get how many results have been found
	if (len(data["items"]) != 0):
		floodAlert = ""
		for alert in data["items"]:
			floodAlert += str(alert["floodAreaID"]) + "," + str(alert["severityLevel"]) + "," + str(alert["timeRaised"]) +","+ str(alert["timeSeverityChanged"]) +"\n"
			#print floodAlert
		return floodAlert
		

def checkThermostat():
	#poll the sensor to get the current temperature
	global currentTemp
	global sensor
	##########################################
	## TODO : Configure to use Temp Sensor  ##
	########################################## 
	currentTemp = sensor.get_temperature()
	if(int(currentTemp) < targetTemp + hysteresis):
		#turn the heating on
		#print("heating should be on")
		turnHeating(action="on")
	elif (int(currentTemp) - int(hysteresis) > targetTemp):
		#turn the heating off
		#print("heating should be off")
		turnHeating(action="off")
	else:
		#Inside hysteresis curve(?)
		print "Not gonna do anything as inside hysteresis curve"

def checkHeatingSchedule():
	global targetTemp
	timeNow = datetime.datetime.strftime(datetime.datetime.now(), '%H:%M')
	dayNow = datetime.datetime.strftime(datetime.datetime.now(), '%a')
	for action in heatingSchedule:
		if (action[0] == dayNow):
			if ( action[1] == timeNow):
				targetTemp = action[2]

def loadXml():
	global heatingSchedule
	tree = ET.parse('/home/pi/python/HomeCentralHeating/heating.xml')
	root = tree.getroot()
	for schedule in root.findall('schedule'):
		day = schedule.find('day').text
		time = schedule.find('time').text
		temp = schedule.find('targetTemp').text
		toAdd = [str(day), str(time), int(temp)]
		heatingSchedule.append(toAdd)
	#print "loaded XML"
	
def initHeating():
	global targetTemp, heatingSchedule
	#eed to scan through the list of heatingSchedule and see which time I currently fall into
	timeNow = datetime.datetime.strftime(datetime.datetime.now(), '%H:%M')
	dayNow = datetime.datetime.strftime(datetime.datetime.now(), '%a')
	#print dayNow
	for event in heatingSchedule:
		if (event[0] == dayNow):
			#on the right day
			#print event
			if (event[1] <= timeNow):
				print event
				targetTemp = event[2]

def exit_handler():
	print 'My application is ending!'
	GPIO.cleanup()

def notificationBar():
	global heatingStatus
	pygame.draw.rect(screen, (0,0,0,), pygame.Rect(0, 0, 480, 20))
	timeNow = create_text(datetime.datetime.strftime(datetime.datetime.now(), '%H:%M'), font_preferences, 24, (255,255,255))
	screen.blit(timeNow, ((480 - timeNow.get_width() -1, 1)))
	title = create_text("Manic House Thermostat", font_preferences, 24, (255,255,255))
	screen.blit(title, (1, 1))
	if (heatingStatus == 1):    #If heating is on, show the heating icon
		screen.blit(flameIcon, (300, 0))

def mainScreen():
	global currentTemp, targetTemp, heatingStatus
	#work out what colour to have the current temp displayed in
	currentColour = colourBlack
	targetColour = colourGreen
	if(int(currentTemp) <= 19):
		currentColour = colourBlue
	if(int(currentTemp) > 19 ):
		currentColour = colourGreen
	if(int(currentTemp) >= 23):
		currentColour = colourRed
	currentTempLarge = create_text(str(currentTemp), font_preferences, 172, currentColour)
	targetTempLarge = create_text(str(targetTemp), font_preferences, 72, targetColour)

	screen.blit(currentTempLarge, ((480 / 2)- currentTempLarge.get_width() /2, (320 /2) - currentTempLarge.get_height() /2))
	screen.blit(targetTempLarge, (480 - targetTempLarge.get_width(), 320 - targetTempLarge.get_height()))

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# create a file handler

handler = logging.FileHandler('/var/log/thermostat.log')
handler.setLevel(logging.DEBUG)

# create a logging format

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# add the handlers to the logger

logger.addHandler(handler)

#logger.info('Hello baby')


#Initial Setup of the GPIO Stuff
#boilerLed = 17
#pumpLed = 27
statusLed = 17 

switchUp = 22
switchDown = 24
switchConfirm = 23
buttonPressed = 0

stationUrl = "http://environment.data.gov.uk/flood-monitoring/id/stations/L0808"
floodUrl = "http://environment.data.gov.uk/flood-monitoring/id/floods?lat=53.551107&long=-1.439991&dist=1"
#floodUrl = "http://environment.data.gov.uk/flood-monitoring/id/floods?min-severity=3"

targetTemp = 21
hysteresis = 1
currentTemp = 19
heatingStatus = 0

sensor = W1ThermSensor(W1ThermSensor.THERM_SENSOR_DS18B20, "0000072b5043")

#images
flameIcon = pygame.image.load("/home/pi/python/HomeCentralHeating/resources/flame.png")
#mailIcon =
#meterReading = 

#software debounce
time_stamp = time.time()

	
	
	#time_stamp = time_now  

heatingSchedule = []

#set the mode
GPIO.setmode(GPIO.BCM)

#set the output pins
#GPIO.setup(boilerLed, GPIO.OUT, initial = 0)
#GPIO.setup(pumpLed, GPIO.OUT, initial = 0)
GPIO.setup(statusLed, GPIO.OUT, initial = 0)		 

#setup the input switches
GPIO.setup(switchUp, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(switchDown, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(switchConfirm, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
time_stamp = time.time() 
GPIO.add_event_detect(switchUp, GPIO.RISING, callback=my_callback, bouncetime=300)
GPIO.add_event_detect(switchDown, GPIO.RISING, callback=my_callback, bouncetime=300)  

atexit.register(exit_handler)

os.environ["SDL_FBDEV"] = "/dev/fb1"
pygame.init()
screen = pygame.display.set_mode((480, 320))
clock = pygame.time.Clock()
done = False
pygame.mouse.set_visible(False)

#colours
colourRed = [100,0,0]
colourOrange = [100,46,0]
colourBlue = [0,58,60]
colourGreen = [0,80,0]
colourBlack = [0,0,0]
colourWhite = [255,255,255]

font_preferences = [
		"Bizarre-Ass Font Sans Serif",
		"They definitely dont have this installed Gothic",
		"Papyrus",
		"Comic Sans MS"]

text = create_text("Hello, World", font_preferences, 72, (0, 128, 0))

loadXml()
initHeating()

while not done:
	for event in pygame.event.get():
		if event.type == pygame.QUIT:
			done = True
		if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
			done = True
	
	screen.fill(colourBlack)
	notificationBar()
	#screen.blit(text,(0, 0))
	checkThermostat()
	checkHeatingSchedule()
	mainScreen()
	#temps = create_text(str(targetTemp) +":"+ str(currentTemp), font_preferences, 25, (255,0,255))
	#screen.blit(temps, (300, 200))
	#time.sleep(1)
	pygame.display.flip()
	clock.tick(12)
