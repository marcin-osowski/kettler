#!/usr/bin/env python3

import config
import kettler

import time

dev = kettler.KettlerDevice(config.KETTLER_DEVICE_SERIAL)
print("Opened Kettler device:")
print("  ID: {}".format(dev.device_id))
print("  Model: {}".format(dev.device_model))
print("  Serial number: {}".format(dev.serial_number))
print("  Version: {}".format(dev.version))
print()

while True:
  print(dev.get_status())
  time.sleep(1.0)

