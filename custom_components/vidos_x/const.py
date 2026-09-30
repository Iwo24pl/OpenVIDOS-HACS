"""Constants for the Vidos X integration."""

DOMAIN = "vidos_x"

# Config entry data / options keys
CONF_DEVICE_IP = "device_ip"
CONF_DEVICE_UID = "device_uid"
CONF_DEVICE_USERNAME = "device_username"
CONF_DEVICE_PASSWORD = "device_password"
CONF_CGI_PORT = "cgi_port"
CONF_SCHEME = "scheme"
CONF_VERIFY_SSL = "verify_ssl"
CONF_ENABLE_ALARM_SWITCH = "enable_alarm_switch"
CONF_ENABLE_LAN_RUNG = "enable_lan_rung"
CONF_ENABLE_RECORD_RUNG = "enable_record_rung"
CONF_RECORD_POLL_INTERVAL = "record_poll_interval"
CONF_CHANNEL_1_NAME = "channel_1_name"
CONF_CHANNEL_2_NAME = "channel_2_name"
CONF_ENABLE_CAMERA = "enable_camera"
CONF_CAMERAS = "cameras"
CONF_CAMERAS_ORIGINAL = "cameras_original"
CONF_DOOR_PASSWORD = "door_password"
CONF_DEFAULT_DOOR = "default_door"
CONF_DEFAULT_LOCK = "default_lock"
CONF_MODEL = "model"
CONF_SOURCE = "source"

SOURCE_MANUAL = "manual"

DEFAULT_CGI_PORT = 443
DEFAULT_SCAN_INTERVAL = 3
MIN_SCAN_INTERVAL = 3
MAX_SCAN_INTERVAL = 3600
DEFAULT_ENABLE_LAN_RUNG = False  # Azeno listener is optional (APP_PARITY D2)
DEFAULT_ENABLE_RECORD_RUNG = True
DEFAULT_RECORD_POLL_INTERVAL = 3
MIN_RECORD_POLL_INTERVAL = 3
MAX_RECORD_POLL_INTERVAL = 30
DEFAULT_CHANNEL_1_NAME = "Channel 1"
DEFAULT_CHANNEL_2_NAME = "Channel 2"
#: Ring log query: enabled cam channels of the IDS9483AW wiring table.
DEFAULT_RECORD_CHANNELS = "1,2"
DEFAULT_ENABLE_CAMERA = True

# Snapshot camera (QUII media port, docs/VIDOS_X_PROTOCOL.md ┬ž4)
SNAPSHOT_TTL_SECONDS = 5  # reuse a freshly grabbed JPEG for this long
SNAPSHOT_TIMEOUT_SECONDS = 7  # whole session; must fit the camera view's 10 s
SNAPSHOT_COOLDOWN_SECONDS = 15  # back off after a failed snapshot
STREAM_KEY_CACHE_SECONDS = 3600  # re-fetch get.device.streamkey rarely

# Physically verified output for IDS9483AW: door=1 (CAM1), lock=1 (DOOR1).
DEFAULT_DOOR = 1
DEFAULT_LOCK = 1

# How long the doorbell binary sensor stays ON after a ring event.
DOORBELL_ON_SECONDS = 15

# Ring events closer together than this are the same physical press seen by
# two sources (record log first, phone-woken Azeno burst ~6 s later).
DOORBELL_RUNG_DEDUP_SECONDS = 10.0

SERVICE_OPEN_DOOR = "open_door"
ATTR_DEVICE_ID = "device_id"
ATTR_DOOR = "door"
ATTR_LOCK = "lock"
ATTR_PASSWORD = "password"

# Bus event fired once per doorbell press: f"{DOMAIN}.{EVENT_DOORBELL_RUNG}"
EVENT_DOORBELL_RUNG = "doorbell_rung"
