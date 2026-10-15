"""Constants for the Week Aqua integration."""

DOMAIN = "weekaqua"

# Config entry option holding the user's own presets:
# {"name": {"levels": [R, G, B, UV] (0-235), "fan": percent or None}}
CONF_PRESETS = "presets"
# Schedule steps, see schedule.py
CONF_SCHEDULE = "schedule"
# "slider" or "box" for the channel and fan controls
CONF_INPUT_MODE = "input_mode"
# Shortest seconds between two fade commands, and the fade curve
CONF_FADE_INTERVAL = "fade_interval"
CONF_FADE_CURVE = "fade_curve"
CURVE_LABELS = {"perceptual": "Natural (follows how eyes see brightness)", "linear": "Linear (equal steps in LED power)"}
FADE_SMOOTHNESS = {"0.5": "Fine (every level)", "10": "Medium (every 10 s at most)", "30": "Coarse (every 30 s at most)", "60": "Very coarse (every minute at most)"}

# The app writes to ffe1 on older Bluetooth boards and fff2 on B3.0 boards.
WRITE_CHAR_PREFIXES = ("0000fff2", "0000ffe1")

# Disconnect this long after the last command so the phone app can connect again.
DISCONNECT_DELAY = 30

# "WEK" protocol (model code 5746): channel value 0x00-0xEB, 0xEB = 100 %
MAX_LEVEL = 235

CMD_SIMPLE_SCHEDULE = bytes.fromhex("FDF1555555555555")
CMD_ADVANCED_SCHEDULE = bytes.fromhex("FDF2555555555555")


CHANNELS = ("red", "green", "blue", "uv")

# The app's built-in presets for this light (StringTools.getPercent, names from strings.xml).
# Values are raw levels R, G, B, UV (0-235).
PRESETS: dict[str, tuple[int, int, int, int]] = {
    "Green": (0x6C, 0xE3, 0x73, 0xEB),
    "Red": (0xA7, 0xB9, 0x74, 0xEB),
    "Mixed": (0x79, 0xDF, 0x74, 0xEB),
    "Gorgeous": (0xC1, 0x5E, 0xBC, 0xEB),
    "Colorful": (0xEB, 0x5E, 0x94, 0xEB),
    "Algae": (0xA3, 0xEB, 0x70, 0x00),
    "Nature": (0x77, 0xEB, 0x77, 0x00),
    "Elegant": (0x83, 0xEB, 0x85, 0x00),
    "Brisk": (0x5E, 0xEB, 0x5E, 0x00),
    "Fresh": (0x59, 0xEB, 0x60, 0x00),
    "Enjoy": (0x6E, 0xEB, 0x65, 0x00),
    "White": (0x7E, 0xEB, 0x69, 0x00),
}


# Power each channel draws at 100 %, as a share of what the light can supply
# (from the app: StringTools.getPower). The app never lets the total exceed 100 %.
POWER_WEIGHTS = (0.39, 0.41, 0.53, 0.11)
CONF_POWER_LIMIT = "power_limit"


def total_power(levels) -> float:
    """Total power in percent of the maximum the light can supply."""
    return sum(w * v / MAX_LEVEL for w, v in zip(POWER_WEIGHTS, levels)) * 100


def limit_power(levels) -> tuple[int, int, int, int]:
    """Scale levels down proportionally so total power is at most 100 %."""
    power = total_power(levels)
    if power <= 100:
        return tuple(int(v) for v in levels)
    factor = 100 / power
    return tuple(int(v * factor) for v in levels)  # round down: never above 100 %


def levels_cmd(levels: tuple[int, int, int, int]) -> bytes:
    """Build a color command from raw levels (0-235)."""
    clamped = [max(0, min(MAX_LEVEL, int(v))) for v in levels]
    return bytes([0xFB, 0xF9, *clamped, 0x55, 0x55])


def color_cmd(r: float, g: float, b: float, uv: float) -> bytes:
    """Build a color command. Inputs are 0.0-1.0."""
    levels = [round(max(0.0, min(1.0, v)) * MAX_LEVEL) for v in (r, g, b, uv)]
    return bytes([0xFB, 0xF9, *levels, 0x55, 0x55])


def fan_cmd(percent: float) -> bytes:
    """Build a fan speed command."""
    level = round(max(0.0, min(100.0, percent)) / 100 * MAX_LEVEL)
    return bytes([0xFC, level, 0x55, 0x55, 0x55, 0x55, 0x55, 0x55])


def clock_cmd(hour: int, minute: int, second: int) -> bytes:
    """Build a clock command. Digits are written as hex (14:30 -> 0x14 0x30)."""

    def bcd(value: int) -> int:
        return ((value // 10) << 4) | (value % 10)

    return bytes([0xFF, bcd(hour), bcd(minute), bcd(second), 0x55, 0x55, 0x55, 0x55])
