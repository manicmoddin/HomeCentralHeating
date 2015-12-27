#!/usr/bin/env python

import pygame
import os, sys
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
		logger.info("Target Temp Increased to %s", targetTemp)
	if(channel == switchDown):
		targetTemp = targetTemp -1
		logger.info("Target Temp Decreased to %s", targetTemp)
	#print targetTemp
	#	buttonPressed = GPIO.input(channel)
	#print buttonPressed

def turnHeating(action):
	global heatingStatus
	handle = open('/dev/ttyAMA0', 'w')
	if( action == "on"):
		if (heatingStatus == 0):
			#turn the heating on, this consists of the pump and the boiler
			#print "Function Turning Heating On!"
			heatingStatus = 1
			logger.info("Heating Turned On")			
			#send the command to node 17
			handle.write("1,1,17s")
			
	else:
		if ( heatingStatus == 1):
			#Turn the heating off
			#print "Funtion Turning Heating Off"
			heatingStatus = 0
			logger.info("Heating Turned Off")
			#send command to node 17
			handle.write("0,0,17s")
			
	handle.close()
			
def helperMap(x, inMin, inMax, outMin, outMax):
	x = float(x)
	return (x - inMin)*(outMax - outMin) // (inMax - inMin) + outMin
	
def drawGuage(value, x, y, width, height, bars, outlineColour, fillColour):
	value = float(value)
	pygame.draw.rect(screen, outlineColour, pygame.Rect(x,y,width,height),1)
	#draw the river Level
	pygame.draw.rect(screen, fillColour,
				pygame.Rect(x+1,height+18,width-2,helperMap(value,0,4,0,-(height-4))))
	#draw the meter markers
	pygame.draw.line(screen, colourWhite, (x, helperMap(1,0,4,y,y+height-2)), (x+width, helperMap(1,0,4,y,y+height-2)), 1)
	pygame.draw.line(screen, colourWhite, (x, helperMap(2,0,4,y,y+height-2)), (x+width, helperMap(2,0,4,y,y+height-2)), 1)
	pygame.draw.line(screen, colourWhite, (x, helperMap(3,0,4,y,y+height-2)), (x+width, helperMap(3,0,4,y,y+height-2)), 1)
	#pygame.draw.line(screen, colourWhite, (x, helperMap(3,0,4,0,height-2)), (x+width, helperMap(3,0,4,0,height-2)), 1)
	#pygame.draw.line(screen, colourWhite, (x, helperMap(3,0,4,0,height-2)), (x+width, helperMap(3,0,4,0,height-2)), 1)
	#pygame.draw.line(screen, colourWhite,(455, 82), (480,82), 1)
	#pygame.draw.line(screen, colourWhite,(455, 145), (480, 145), 1)
	#pygame.draw.line(screen, colourWhite,(455, 207), (480, 207), 1)
	

def checkRiverLevel():
	global riverLevelInt
	GPIO.output(statusLed, 1)
	response = urllib.urlopen(stationUrl)
	data = json.load(response)
	riverLevel = str(data["items"]["measures"]["latestReading"]["dateTime"]) +","+str(data["items"]["measures"]["latestReading"]["value"])
	GPIO.output(statusLed, 0)
	#return riverLevel
	river = riverLevel.split(",")
	logger.debug("River Level = %s", river[1])
	riverInt = river[1]
	type(riverInt)
	riverLevelInt = riverInt

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
		print floodAlert
	else:
		print "No Flood alerts"
		

def checkThermostat():
	#poll the sensor to get the current temperature
	global currentTemp
	global sensor
	##########################################
	## TODO : Configure to use Temp Sensor  ##
	########################################## 
	currentTemp = int(sensor.get_temperature())
	if(int(currentTemp) <= (targetTemp - hysteresis)):
		#turn the heating on
		#print("heating should be on")
		turnHeating(action="on")
		logger.debug("Heating Should be on T=%s, C=%s",targetTemp, currentTemp)
	elif (int(currentTemp) >= (targetTemp + hysteresis)):
		#turn the heating off
		#print("heating should be off")
		turnHeating(action="off")
		logger.debug("Heating Should be off T=%s, C=%s",targetTemp, currentTemp)
	else:
		#Inside hysteresis curve(?)
		#print "Not gonna do anything as inside hysteresis curve"
		logger.debug("temp inside hysteresis T=%s, C=%s",targetTemp, currentTemp)

def checkHeatingSchedule():
	global targetTemp
	timeNow = datetime.datetime.strftime(datetime.datetime.now(), '%H:%M')
	dayNow = datetime.datetime.strftime(datetime.datetime.now(), '%a')
	for action in heatingSchedule:
		if (action[0] == dayNow):
			#logger.debug("Is in correct day")
			if ( action[1] == timeNow):
				targetTemp = action[2]
				logger.debug("Found the time, chaging target temp")
				logger.info("Set the target temp to %s", targetTemp)

def loadXml():
	global heatingSchedule
	try:
		tree = ET.parse('/home/pi/python/HomeCentralHeating/heating.xml')
	except:
		logger.exception('Unable to load XML File')
		raise
	root = tree.getroot()
	for schedule in root.findall('schedule'):
		day = schedule.find('day').text
		time = schedule.find('time').text
		temp = schedule.find('targetTemp').text
		toAdd = [str(day), str(time), int(temp)]
		heatingSchedule.append(toAdd)
		logger.debug("Added %s, %s, %s to heatingSchedule", day, time, temp)
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
				logger.debug("Found the time, chaging target temp")
				logger.info("Set the target temp to %s", targetTemp)

def exit_handler():
	#print 'My application is ending!'
	logger.exception('Been told to die')
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
		
	if(targetTemp <= 17):
		targetColour = colourBlue
	if(targetTemp > 17):
		targetColour = colourGreen
	if(targetTemp > 21):
		targetColour = colourRed
	
	currentTempLarge = create_text(str(currentTemp), font_preferences, 172, currentColour)
	targetTempLarge = create_text(str(targetTemp), font_preferences, 72, targetColour)

	screen.blit(currentTempLarge, ((480 / 2)- currentTempLarge.get_width() /2, (320 /2) - currentTempLarge.get_height() /2))
	screen.blit(targetTempLarge, (480 - targetTempLarge.get_width(), 320 - targetTempLarge.get_height()))
	
	### RIVER LEVEL ###
	#drawGuage(riverLevelInt, 455, 20, 25, 250, 4, colourWhite, colourBlue)
	drawGuage(riverLevelInt, 455, 20, 25, 250, 4, colourWhite, colourBlue)
	
	
	
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# create a file handler

#handler = logging.FileHandler('/var/log/thermostat.log')
handler = logging.StreamHandler(sys.stdout)

# create a logging format

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
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

riverLevelInt = 0

#load temp sensor
try:
	sensor = W1ThermSensor(W1ThermSensor.THERM_SENSOR_DS18B20, "0000072b5043")
except:
	logger.exception('Temp Sensor error')
	raise

#images
try:
	flameIcon = pygame.image.load("/home/pi/python/HomeCentralHeating/resources/flame.png")
	#mailIcon =
	#meterReading = 
except:
	logger.exception('Unable to load Image(s)')
	raise


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
colourRed = [255,0,0]
colourOrange = [255,100,0]
colourYellow = [255,255,0]
colourCyan = [0,255,255]
colourBlue = [0,0,255]
colourGreen = [0,255,0]
colourMagenta = [255,0,255]
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
checkRiverLevel()
tw = time.time()
tf = time.time()
tr = time.time()

while not done:
	for event in pygame.event.get():
		if event.type == pygame.QUIT:
			done = True
		if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
			done = True
	
	#check river Level
	timeRiver = time.time()
	if (timeRiver - tr >= 900):
		logger.debug("Checking River Level")
		checkRiverLevel()
		tr = time.time()
		
	#check floodAlerts Level
	timeFlood = time.time()
	if (timeFlood - tf >= 900):
		logger.debug("Checking Flood Alert")
		checkFloodAlert()
		tf = time.time()
	
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
