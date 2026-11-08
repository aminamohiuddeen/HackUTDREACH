# Display-only for now:
# - ZONE_WEIGHTING is shown in /api/config but the classifier currently
#   uses a hardcoded `zone == "residential"` check. Wiring this in is a
#   behavior change tracked separately.
# - UNIT_TYPE_MAPPING matches the coordinator's hardcoded mapping today,
#   but the coordinator does not read from config. Both will be unified
#   after the hackathon.
"""Responder-facing thresholds for REACH.

Thresholds are set by the responding agency's SOP; these are the defaults.
Read values as `config.X` at call time (never `from config import X`) so
overrides and test monkeypatches take effect.
"""

ANOMALY_SIZE_CM2 = {"min": 400, "max": 8000}
ZONE_WEIGHTING = {"residential": 1, "industrial": 0, "road": 0, "unknown": 0}

# NOTE: despite the name, this threshold gates possible_person/verify.
# In the current classifier, only a survey response produces likely_person.
# Kept for API stability; the semantics are "signals required for the
# non-trivial classification path".
SIGNALS_REQUIRED_FOR_LIKELY_PERSON = 2

UNIT_TYPE_MAPPING = {
    "trapped": ["FIRE", "SAR"],
    "injured": ["EMS"],
    "breathing_difficulty": ["EMS"],
    "immediate_help": ["EMS"],
    "others_present": ["SAR"],
    "verify": ["SAR"],
}
VERIFY_WINDOW_SECONDS = 300
