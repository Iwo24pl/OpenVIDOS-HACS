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
CONF_RTSP_URL = "rtsp_url"
CONF_DOOR_PASSWORD = "door_password"
CONF_MODEL = "model"
CONF_SOURCE = "source"

SOURCE_CLOUD = "cloud"
SOURCE_MANUAL = "manual"

DEFAULT_CGI_PORT = 443
DEFAULT_SCAN_INTERVAL = 10
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 3600
DEFAULT_ENABLE_LAN_RUNG = True

# How long the doorbell binary sensor stays ON after a ring event.
DOORBELL_ON_SECONDS = 15

SERVICE_OPEN_DOOR = "open_door"
ATTR_DEVICE_ID = "device_id"
ATTR_DOOR = "door"
ATTR_PASSWORD = "password"

# Bus event fired once per doorbell press: f"{DOMAIN}.{EVENT_DOORBELL_RUNG}"
EVENT_DOORBELL_RUNG = "doorbell_rung"
