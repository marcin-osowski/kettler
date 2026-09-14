#!/usr/bin/env python3

def main():
  import config
  import kettler
  import serial

  print("WARNING: Stop the logger before using this REPL; do not use it during exercise.")
  print("Opening the port sends ID/KI/SN/VE, then RS resets the console automatically.")
  print("Commands are unrestricted and may change resistance or reset exercise data.", flush=True)
  dev = None
  try:
    dev = kettler.KettlerDevice(config.KETTLER_DEVICE_SERIAL)
    print("Opened Kettler device:")
    print("  ID: {}".format(dev.device_id))
    print("  Model: {}".format(dev.device_model))
    print("  Serial number: {}".format(dev.serial_number))
    print("  Version: {}".format(dev.version))
    print("Resetting device...")
    dev.reset()
    print("Done.")
    print(kettler.KettlerDevice.__doc__)
    print("Enter any protocol command. Ctrl-D or Ctrl-C exits; responses use repr() to show framing.")
    while True:
      command = input("> ")
      if not command.strip():
        continue
      response = dev._send_command_multi_line_resp(command, check_noerror=False)
      print(repr(response))
  except (EOFError, KeyboardInterrupt):
    print("\nLeaving REPL.")
  except (serial.SerialException, kettler.SerialPortOpenError,
          kettler.InvalidDeviceResponse, kettler.ErrorDeviceResponse, UnicodeError) as exc:
    print("Communication failed: {}. Command outcome may be unknown; not retrying.".format(exc))
    return 1
  finally:
    if dev is not None:
      dev.close()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())

