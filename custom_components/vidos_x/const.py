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

SERVICE_OPEN_DOOR = "open_door"
ATTR_DEVICE_ID = "device_id"
ATTR_DOOR = "door"
ATTR_PASSWORD = "password"
