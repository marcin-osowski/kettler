import time
import RPi.GPIO as GPIO

import config

def init_activity():
  GPIO.setmode(GPIO.BCM)
  GPIO.setup(config.ACTIVITY_PIN_BCM, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

def read_activity_pin():
  all_zero = True
  all_one = True
  for i in range(5):
    result = GPIO.input(config.ACTIVITY_PIN_BCM)
    if result != 0:
      all_zero = False
    if result != 1:
      all_one = False
    time.sleep(0.1)
  
  if all_zero:
    return 0
  if all_one:
    return 1
  return None

