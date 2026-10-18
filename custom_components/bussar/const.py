"""Konstanter för Bussar."""

DOMAIN = "bussar"

CONF_STOP_ID = "stop_id"
CONF_STOP_NAME = "stop_name"
CONF_LINE = "line"
CONF_PLATFORM = "platform"

SUBENTRY_LINE = "line"

CONF_WALK_MINUTES = "walk_minutes"
CONF_RUN_MINUTES = "run_minutes"
CONF_WINDOW_MINUTES = "window_minutes"

CONF_VEHICLE_API_KEY = "vehicle_api_key"

# Bronze-nivån för GTFS Regional Realtime är 30 000 anrop per månad; marginal för tester.
POSITIONS_MONTHLY_LIMIT = 28_000
USAGE_DEPARTURES = "departures"
USAGE_POSITIONS = "positions"
POSITIONS_KEY_ISSUE = "positions_key_invalid"
