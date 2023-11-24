import time
import serial

class SerialPortOpenError(Exception):
  """We could not open the serial port."""
  pass

class InvalidDeviceResponse(Exception):
  """We couldn't parse the response from the device."""
  pass

class ErrorDeviceResponse(Exception):
  """Device returned an error."""
  pass

class KettlerStatus(object):
  """Status of the exercise."""

  def __init__(self, heart_rate_bpm, exercise_rpm, speed_kmph,
               distance_km, dest_power_watt, energy_kjoule,
               time_elapsed_sec, real_power_watt):
    self.heart_rate_bpm = heart_rate_bpm
    self.exercise_rpm = exercise_rpm
    self.speed_kmph = speed_kmph
    self.distance_km = distance_km
    self.dest_power_watt = dest_power_watt
    self.energy_kjoule = energy_kjoule
    self.time_elapsed_sec = time_elapsed_sec
    self.real_power_watt = real_power_watt

  @staticmethod
  def from_array(resp, orig_resp):
    if len(resp) != 8:
      raise InvalidDeviceResponse("Invalid response from device: {}".format(orig_resp))

    try:
      # resp[6] is mm:ss, let's parse it to seconds
      mm, ss = resp[6].split(":")
    except ValueError:
      raise InvalidDeviceResponse("Invalid response from device: {}".format(orig_resp))

    try:
      status = KettlerStatus(
        heart_rate_bpm=int(resp[0]),
        exercise_rpm=int(resp[1]),
        speed_kmph=int(resp[2]) / 10.0,
        distance_km=int(resp[3]) / 10.0,
        dest_power_watt=int(resp[4]),
        energy_kjoule=int(resp[5]),
        time_elapsed_sec=int(mm) * 60 + int(ss),
        real_power_watt=int(resp[7]),
      )
    except ValueError:
      raise InvalidDeviceResponse("Invalid response from device: {}".format(orig_resp))
    return status

  def __str__(self):
    return "Heart rate: {}bpm, RPM: {}, Speed: {}km/h, Distance: {}km, Dest power: {}W, Energy: {}kJ, Time: {}s, Real power: {}W".format(
      self.heart_rate_bpm, self.exercise_rpm, self.speed_kmph,
      self.distance_km, self.dest_power_watt, self.energy_kjoule,
      self.time_elapsed_sec, self.real_power_watt)


class KettlerDevice(object):
  """A Kettler device.

  Tested on Kettler Unix E.

  Commands that read the state of the device:
    ID: Device ID.
    KI: Device model.
    SN: Serial number.
    TR: Returns device's time.
    ST: Returns the status of the exercise.
    ES1: Returns the status of the exercise.
    ES2: Unknown.
    CA: Unknown.
    BS: Unknown, but looks very similar to ST.
    KR: Unknown.
    RF: Returns some XML. Multi-line response.
    VE: Device version.
    VS: Unknown.

  Commands that change the state of the device:
    RS: Reset device.
    CM: Enter the command mode, allows to set things like power, time, ...
    EE: Unknown, but it clearly changes state, as error messages change.
    PD: Put Distance. The argument is the distance in 0.1km,
        the values are between 0 and 999.
    PT: Put Time. The argument is the time in seconds, the values are
        between 0 and 9959. First two digits describe minutes last two
        digits describe seconds. If the number of seconds is greater
        than 59 it will be reduced to 59.
    PW: Put Watt. The argument is power in watts, the values are between
        25 and 400 in 5 steps. The values less than 25 are converted to 25.
        The values greater than 400 are converted to 400.
    PP: Unknown.
    PI: Put Incline. Not tested, my device does not support this.
    LB: Unknown.
    SP: Unknown.
    TS: Unknown.

  """

  def __init__(self, port):
    """Initialize the KettlerDevice object.

    Args:
      port: The serial port to use, as a string.
    """
    self.ser = serial.Serial()
    self.ser.port = port
    self.ser.baudrate = 57600
    self.ser.bytesize = serial.EIGHTBITS
    self.ser.parity = serial.PARITY_NONE
    self.ser.stopbits = serial.STOPBITS_ONE
    self.ser.timeout = 1.0
    self.ser.open()
    if not self.ser.is_open:
      raise SerialPortOpenError("Could not open serial port {}".format(port))

    self.device_id = None
    self.device_model = None
    self.serial_number = None
    self._load_device_details()
    if not self.device_id:
      raise InvalidDeviceResponse("Could not get device ID. Is the device connected?")

  def __del__(self):
    if self.ser.is_open:
      self.ser.close()

  def _load_device_details(self):
    self.device_id = self._send_command("ID")
    self.device_model = self._send_command("KI")
    self.serial_number = self._send_command("SN")
    self.version = self._send_command("VE")

  def _send_command(self, command, check_noerror=True):
    """Send a command to the device and return the response."""
    if isinstance(command, str):
      command = command.encode()
    self.ser.write(command + b"\r\n")
    response = self.ser.read_until(b"\r\n")
    # Strip trailing \r\n, if present
    if response[-2:] == b"\r\n":
      response = response[:-2]
    if check_noerror and response == b"ERROR":
      raise ErrorDeviceResponse("Device returned an error for command {}".format(command))
    return response.decode()

  def _send_command_multi_line_resp(self, command, check_noerror=True):
    """Send a command to the device and return the response.
    
    This method is used for commands that return multiple lines of response.
    It will read until the device does not respond anymore.
    This is slow, as we have to wait for the timeout to occur.
    """
    if isinstance(command, str):
      command = command.encode()
    self.ser.write(command + b"\r\n")
    # Try reading, until the device does not respond anymore
    response = b""
    while True:
      read = self.ser.read()
      if len(read) == 0:
        break
      response += read
    if check_noerror and (response == b"ERROR\r\n" or response == b"ERROR"):
      raise ErrorDeviceResponse("Device returned an error for command {}".format(command))
    return response.decode()

  def get_status(self):
    """Get the status of the exercise."""
    orig_resp = self._send_command("ST")
    resp = orig_resp.split("\t")
    return KettlerStatus.from_array(resp, orig_resp)

  def get_status_alternative(self):
    """Get the status of the exercise, alternative command."""
    orig_resp = self._send_command("ES1")
    resp = orig_resp.split("\t")
    if len(resp) != 12:
      raise InvalidDeviceResponse("Invalid response from device: {}".format(orig_resp))
    # resp[0 .. 3] are unknown
    # resp[3] seems to be doing something, but I don't know what
    return KettlerStatus.from_array(resp[4:], orig_resp)

  def reset(self):
    """Reset the device.

    This method will reset the device and wait 2 seconds for it to be ready
    again. Note that it may not be ready after 2 seconds, but it is likely.
    """
    self._send_command("RS")
    time.sleep(2.0)

  def get_device_time(self):
    """Get the device time."""
    return self._send_command("TR")

  def enter_command_mode(self):
    """Enter the command mode.

    This mode allows to set things like power, time, ...
    Don't know how to leave it though, except via a reset.

    Example usage:
      device.enter_command_mode()
      device.put_time(5*60 + 30)
      device.put_watts(100)
      device.put_distance(10.0)
    """
    self._send_command("CM")

  def put_distance(self, distance_in_km):
    """Set the distance in km."""
    distance_in_100m = int(distance_in_km * 10)
    if distance_in_100m < 0:
      raise ValueError("Distance must be positive")
    if distance_in_100m > 9999:
      # Maybe it can be more, but I don't know.
      raise ValueError("Distance must be less than 999.9 km")
    self._send_command("PD {}".format(distance_in_100m))

  def put_watts(self, watts):
    """Set the watts."""
    watts = int(watts)
    if watts < 0:
      raise ValueError("Watts must be positive")
    if watts > 999:
      # Maybe it can be more, but I don't know.
      raise ValueError("Watts must be less than 999")
    self._send_command("PW {}".format(watts))

  def put_time(self, seconds):
    """Set the time in seconds."""
    seconds = int(seconds)
    if seconds < 0:
      raise ValueError("Time must be positive")
    if seconds > 9959:
      # Maybe it can be more, but I don't know.
      raise ValueError("Time must be less than 9959 seconds")
    minutes = seconds // 60
    seconds = seconds % 60
    self._send_command(f"PT {minutes:02d}{seconds:02d}")
