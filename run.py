#!/usr/bin/env python3

import config
import kettler
import mqtt_publisher

import time

def main():
  """Main function. Restarted externally if it fails."""

  if config.ACTIVITY_PIN_BCM is not None:
    import activity
    activity.init_activity()

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

  print("Sending initial status...")
  status = dev.get_status()
  mqtt.publish_status(status)
  time.sleep(1.0)

  print("Starting main loop...")

  while True:
    if config.ACTIVITY_PIN_BCM is not None:
      # We need to wait for raising edge on the activity
      # pin before starting reading.
      print("Waiting for a raising edge on the activity pin...")
      import activity
      while activity.read_activity_pin() != 0:
        time.sleep(0.5)
      while activity.read_activity_pin() != 1:
        time.sleep(0.5)
      print("Device got activated!")

      # It needs some time to start.
      time.sleep(10.0)
      print("Trying to read the device...")
      dev.get_status()
      print("OK. Now sending data to MQTT")

    last_use_time = time.time()

    while True:
        status = dev.get_status()
        mqtt.publish_status(status)

        is_in_use = status.speed_kmph > 0.0
        if is_in_use:
          last_use_time = time.time()

        # If it hasn't been used for a while, reset the device
        # and go back to waiting for raising edge.
        if time.time() - last_use_time > config.IDLE_DEVICE_RESET_TIME:
          print("No activity for a while. Resetting device...")
          dev.reset()
          time.sleep(5.0)
          print("Done.")
          break  # Go wait for the raising edge again.

        time.sleep(config.MQTT_UPDATE_TIME)


if __name__ == "__main__":
  while True:
    try:
      main()
    except Exception as e:
      print("Exception: {}".format(e))
      print("Restarting in 10 seconds...")
      time.sleep(10.0)
