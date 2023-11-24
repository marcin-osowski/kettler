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

print("Resetting device...")
dev.reset()
print("Done.")

print()
print("Docstring of the KettlerDevice class:")
print(kettler.KettlerDevice.__doc__)
print()
print()

print("Enter commands to send down the serial port. The device response will be printed.")
while True:
  command = input(">")
  resp = dev._send_command_multi_line_resp(command, check_noerror=False)
  print(resp)

