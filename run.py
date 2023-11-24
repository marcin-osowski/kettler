#!/usr/bin/env python3

import config
import kettler
import mqtt_publisher

import time

def main():
  """Main function. Restarted externally if it fails."""

  dev = kettler.KettlerDevice(config.KETTLER_DEVICE_SERIAL)
  print("Opened Kettler device:")
  print("  ID: {}".format(dev.device_id))
  print("  Model: {}".format(dev.device_model))
  print("  Serial number: {}".format(dev.serial_number))
  print("  Version: {}".format(dev.version))
  print()

  print("Connecting to MQTT broker...")
  mqtt = mqtt_publisher.MqttPublisher(
    client_id=config.MQTT_CLIENT_ID,
    username=config.MQTT_USERNAME,
    password=config.MQTT_PASSWORD,
    host=config.MQTT_HOST,
    port=config.MQTT_PORT,
  )
  time.sleep(1.0)

  print("Sending MQTT discovery messages...")
  mqtt.send_discovery_messages(
    model=dev.device_model,
    serial_number=dev.serial_number,
    sw_version=dev.version,
    hw_version=dev.device_id,
  )
  time.sleep(1.0)

  print("Starting main loop...")
  last_use_time = None
  last_publish_time = None
  is_in_use = False
  was_in_use = False

  while True:
    status = dev.get_status()
    # Speed indicates whether the device is actually in use
    was_in_use = is_in_use
    is_in_use = status.speed_kmph > 0.0
    if is_in_use and not was_in_use:
      print("Device is now in use.")

    if is_in_use or was_in_use:
      # Device that is in use gets fast publishing
      last_use_time = time.time()
      mqtt.publish_status(dev.get_status())
      last_publish_time = time.time()

    else:
      # Not in use. Slower publish.
      if last_publish_time is None or (time.time() - last_publish_time > config.IDLE_MQTT_UPDATE_TIME):
        mqtt.publish_status(dev.get_status())
        last_publish_time = time.time()

      # If it hasn't been used for a while, reset the device.
      if last_use_time is not None:
        if time.time() - last_use_time > config.IDLE_DEVICE_RESET_TIME:
          print("Resetting device...")
          dev.reset()
          time.sleep(5.0)
          last_use_time = None
          last_publish_time = None
          print("Done.")

    # Maximum frequency of updates when in use
    time.sleep(config.BUSY_MQTT_UPDATE_TIME)


if __name__ == "__main__":
  while True:
    try:
      main()
    except Exception as e:
      print("Exception: {}".format(e))
      print("Restarting in 10 seconds...")
      time.sleep(10.0)
