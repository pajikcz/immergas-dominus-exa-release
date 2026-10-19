"""Preview a measured room-temperature input. No protocol encoding or network I/O.

The actual Dominus external-measurement input is NOT commissioned. Selecting a
source here does not prove that Dominus/CAR can use it for native regulation.
"""
import math


def _finite_number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def preview_measurement(source_states, selected_source):
    """Select one source, never average or substitute the requested setpoint.

    source_states maps sensor entity IDs to state values. Unknown, unavailable,
    nonnumeric and nonfinite readings produce no temperature candidate. This
    preview expects Celsius; unit conversion and live HA wiring are not included.
    """
    temperature = _finite_number(source_states.get(selected_source))
    return {"source": selected_source, "candidate_celsius": temperature,
            "status": "simulation_ready" if temperature is not None else "unavailable",
            "simulation_only": True, "transmitted_to_boiler": False}


def preview_compensated_target(*, requested_celsius, car_celsius, ha_celsius,
                               target_min, target_max):
    """Preview setpoint translation, NOT a measured-sensor override or PID.

    Caller-supplied limits are simulation assumptions, not discovered device bounds.
    No clipping: clipping would break even the simple error-equivalence equation.
    Does not model freshness, protocol quantization, dynamics or safe live fallback.
    """
    result = {"kind": "target_compensation", "candidate_target_celsius": None,
              "simulation_only": True, "transmitted_to_boiler": False,
              "native_behavior_verified": False}
    values = [_finite_number(v) for v in
              (requested_celsius, car_celsius, ha_celsius, target_min, target_max)]
    if any(v is None for v in values):
        return dict(result, status="unavailable")
    requested, car, measured, low, high = values
    if low > high:
        return dict(result, status="invalid_limits")
    candidate = requested + car - measured
    if not low <= requested <= high or not low <= candidate <= high:
        return dict(result, status="outside_simulated_limits")
    return dict(result, status="simulation_ready", candidate_target_celsius=candidate,
                requested_error_celsius=requested - measured,
                controller_error_celsius=candidate - car)
