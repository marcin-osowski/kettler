import math
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
    ST: Returns the normal logger record. In command mode, its distance, energy,
        and time fields may contain configured targets rather than accumulated
        exercise values.
    ES1: Returns four unknown fields followed by an eight-field exercise
        record. Unlike ST, its energy, distance, and time fields remained zero
        when idle targets were configured, so it is not an ST alias.
    CA: Unknown.
    KR: Unknown.
    RF: Returns some XML. Multi-line response.
    VE: Device version.
    VS: Unknown.

  Commands with unresolved semantics and side effects:
    ES2: Returns six fields.
    BS: Returns eight status-like fields, not equivalent to ST.

  Commands that change the state of the device:
    RS: Reset device.
    CM: Enter command mode; first entry can clear the workout and restore 25 W.
    EE: Unknown, but it clearly changes state, as error messages change.
    PD: Put Distance. The argument is distance in 0.1 km, clamped by this
        device to 0..4999 (0..499.9 km).
    PE: Put Energy. The argument is an energy target in kJ, clamped to
        0..9999 by this device.
    PT: Put Time. The protocol argument is minutes followed by two seconds
        digits, not a fixed-width field. This device supports 0..199:59.
    PW: Put Watt. This device clamps to 25..400 W and rounds to the nearest
        5 W (half-step behavior was not tested because integer inputs suffice).
    PP: Unsupported on this device; tested values returned ERROR.
    PI: Put Incline. Not tested, my device does not support this.
    LB: Unknown.
    SP: Unknown.
    TS: Unknown.

  Bare PD, PE, PT, and PW are state-changing setters, not status reads: in
  command mode they reset their targets to zero distance, zero energy, 00:00,
  and 25 W. Setters can return a status-shaped response even when they do not
  apply; for example, PW 30 did not change the target until CM had been sent.
  Verify with a subsequent status read when successful application matters.

  """

  def __init__(self, port):
    """Initialize the KettlerDevice object.

    Args:
      port: The serial port to use, as a string.
    """
    self.ser = serial.Serial()
    try:
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
    except BaseException:
      # Do not retain the port if startup queries or validation fail.
      try:
        self.close()
      except Exception:
        pass
      raise

  def __del__(self):
    try:
      self.close()
    except Exception:
      # Destructors cannot report cleanup failures usefully.
      pass

  def close(self):
    """Close the serial port, including after partial initialization."""
    ser = getattr(self, "ser", None)
    if ser is not None and ser.is_open:
      ser.close()

  def _load_device_details(self):
    self.device_id = self._load_device_id()
    self.device_model = self._send_command("KI", require_complete=True)
    if self._startup_id_retried and self.device_model == self.device_id:
      # A response to the first ID can arrive after the bounded second ID.
      # Consume KI's already-requested response without transmitting again.
      self.device_model = self._read_response(b"KI", require_complete=True)
    if not self.device_model or self.device_model == self.device_id:
      raise InvalidDeviceResponse("Missing or misaligned KI response")
    self.serial_number = self._send_command("SN", require_complete=True)
    if not self.serial_number:
      raise InvalidDeviceResponse("Missing SN response")
    self.version = self._send_command("VE", require_complete=True)
    if not self.version:
      raise InvalidDeviceResponse("Missing VE response")

  def _load_device_id(self):
    """Read ID, allowing one bounded recovery from an empty first response.

    Opening the port alone did not wake the tested console. One cold-screen
    observation returned an empty first ID response and answered a second ID
    five seconds later. A complete delayed first response is consumed before
    deciding whether a second ID write is needed, so it cannot become KI's
    response.
    """
    self._startup_id_retried = False
    device_id = self._send_command("ID", require_complete=True)
    if device_id:
      return device_id

    time.sleep(5.0)
    waiting = getattr(self.ser, "in_waiting", 0)
    if waiting:
      delayed = self.ser.read_until(b"\r\n")
      if delayed.endswith(b"\r\n"):
        delayed = delayed[:-2]
        if delayed:
          if delayed == b"ERROR":
            raise ErrorDeviceResponse("Device returned an error for command b'ID'")
          return delayed.decode()
      if delayed:
        raise InvalidDeviceResponse("Incomplete delayed response to startup ID")

    self._startup_id_retried = True
    device_id = self._send_command("ID", require_complete=True)
    if not device_id:
      raise InvalidDeviceResponse("Could not get device ID. Is the device connected?")
    return device_id

  def _send_command(self, command, check_noerror=True, require_complete=False):
    """Send a command to the device and return the response."""
    if isinstance(command, str):
      command = command.encode()
    self.ser.write(command + b"\r\n")
    return self._read_response(command, check_noerror, require_complete)

  def _read_response(self, command, check_noerror=True, require_complete=False):
    """Read one response for a command that has already been transmitted."""
    response = self.ser.read_until(b"\r\n")
    if require_complete and response and not response.endswith(b"\r\n"):
      raise InvalidDeviceResponse("Incomplete response to {}".format(command))
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
    """Get the ST record used by the logger.

    In command mode, distance, energy, and time can be configured targets rather
    than accumulated exercise values.
    """
    orig_resp = self._send_command("ST")
    resp = orig_resp.split("\t")
    return KettlerStatus.from_array(resp, orig_resp)

  def get_status_alternative(self):
    """Get the ES1 record; its fields are not semantically identical to ST.

    The first four fields are unknown. In idle command-mode tests, the parsed
    energy, distance, and time remained zero while ST exposed configured
    targets.
    """
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
    First entry returned ACK and cleared a completed workout, restoring 25 W.
    Repeated CM in command mode returned RUN and preserved configured targets.
    Do not use it as a harmless wake command.
    Don't know how to leave it though, except via a reset.
    A status-shaped setter response does not prove the target was applied;
    verify the resulting state when that matters.

    Example usage:
      device.enter_command_mode()
      device.put_time(5*60 + 30)
      device.put_watts(100)
      device.put_distance(10.0)
    """
    self._send_command("CM")

  def put_distance(self, distance_in_km):
    """Set 0..499.9 km, truncating fractional 0.1 km units toward zero."""
    distance_in_km = self._bounded_number(
      distance_in_km, 0, 499.9, "Distance", "km")
    distance_in_100m = int(distance_in_km * 10)
    self._send_command("PD {}".format(distance_in_100m))

  def put_watts(self, watts):
    """Set 25..400 W; fractional input is truncated before device rounding."""
    watts = self._bounded_number(watts, 25, 400, "Power", "W")
    self._send_command("PW {}".format(int(watts)))

  def put_time(self, seconds):
    """Set 0..11999 seconds, truncating fractional seconds toward zero."""
    seconds = int(self._bounded_number(seconds, 0, 11999, "Time", "seconds"))
    minutes = seconds // 60
    seconds = seconds % 60
    self._send_command(f"PT {minutes:02d}{seconds:02d}")

  def put_energy(self, energy_kjoule):
    """Set a 0..9999 kJ target, truncating fractional kJ toward zero."""
    energy_kjoule = self._bounded_number(
      energy_kjoule, 0, 9999, "Energy", "kJ")
    self._send_command("PE {}".format(int(energy_kjoule)))

  @staticmethod
  def _bounded_number(value, minimum, maximum, name, unit):
    """Validate a wrapper value before any lossy integer conversion."""
    try:
      value = float(value)
    except (TypeError, ValueError, OverflowError):
      raise ValueError("{} must be a finite number".format(name))
    if not math.isfinite(value):
      raise ValueError("{} must be a finite number".format(name))
    if value < minimum or value > maximum:
      raise ValueError(
        "{} must be between {} and {} {}".format(name, minimum, maximum, unit))
    return value
