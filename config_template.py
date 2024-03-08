import os.path
CURRENT_DIR=os.path.dirname(os.path.abspath(__file__))

KETTLER_DEVICE_SERIAL=""

MQTT_CLIENT_ID="kettler"
MQTT_USERNAME="kettler"
MQTT_PASSWORD=""
MQTT_HOST="homeassistant"
# TLS is expected.
MQTT_PORT=8883

# Times in seconds
MQTT_UPDATE_TIME=5.0
IDLE_DEVICE_RESET_TIME=300.0

# The pin to poll for activity. Device start will be
# detected by a rising edge on this pin.
# Set to None if the pin is not used, the device
# will be polled constantly then.
ACTIVITY_PIN_BCM=None

# DB file that will store stats
DB_FILE=os.path.join(CURRENT_DIR, "db.sqlite3")

# HTTP server
HTTP_HOST="127.0.0.1"
HTTP_PORT=8080
