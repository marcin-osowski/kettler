import json
import paho.mqtt.client

class MqttPublisher:

  def __init__(self, client_id, username, password, host, port):
    self._client = paho.mqtt.client.Client(client_id=client_id)
    self._client.tls_set()
    self._client.on_connect = MqttPublisher._on_connect
    self._client.username_pw_set(username=username, password=password)
    self._client.connect(host=host, port=port, keepalive=60)
    self._client.loop_start()

  @staticmethod
  def _on_connect(client, userdata, flags, rc):
    if rc != 0:
      print(f"Failed to connect to MQTT, return code: {rc}")
      return

  def send_discovery_messages(self, model, serial_number, sw_version, hw_version):
    def send_one(field_name, field_unit, field_description):
      discovery_topic = 'homeassistant/sensor/kettler/kettler_{}/config'.format(field_name)
      discovery_payload = {
        "name": field_description,
        "state_topic": "home/kettler/status",
        "unit_of_measurement": field_unit,
        "unique_id": "kettler/{}".format(field_name),
        "value_template": "{{ value_json." + field_name + " }}",
        "device": {
          "identifiers": ["serial_number", serial_number],
          "name": "Kettler",
          "model": model,
          "manufacturer": "Kettler",
          "sw_version": sw_version,
          "hw_version": hw_version,
        },
      }
      self._client.publish(
        topic=discovery_topic,
        payload=json.dumps(discovery_payload),
        retain=True,
      )

    send_one("heart_rate_bpm", "bpm", "Heart Rate")
    send_one("exercise_rpm", "rpm", "Exercise RPM")
    send_one("speed_kmph", "km/h", "Speed")
    send_one("distance_km", "km", "Distance")
    send_one("dest_power_watt", "W", "Destination Power")
    send_one("energy_kjoule", "kJ", "Energy")
    send_one("time_elapsed_sec", "s", "Time Elapsed")
    send_one("real_power_watt", "W", "Real Power")

  def publish_status(self, kettler_status):
    payload = {
      "heart_rate_bpm": kettler_status.heart_rate_bpm,
      "exercise_rpm": kettler_status.exercise_rpm,
      "speed_kmph": kettler_status.speed_kmph,
      "distance_km": kettler_status.distance_km,
      "dest_power_watt": kettler_status.dest_power_watt,
      "energy_kjoule": kettler_status.energy_kjoule,
      "time_elapsed_sec": kettler_status.time_elapsed_sec,
      "real_power_watt": kettler_status.real_power_watt,
    }
    self._client.publish(
      topic="home/kettler/status",
      payload=json.dumps(payload),
    )
