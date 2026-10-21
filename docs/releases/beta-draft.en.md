# Experimental beta — draft release notes

[Česky](beta-draft.cs.md) · [Getting started](../getting-started.en.md)

**Draft for approval only.** This is not a published release or an announcement of
public availability. The public beta version/tag has not been selected. License: MIT,
with the complete upstream notice in [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md).

## Intended audience

Technically experienced users with matching Dominus/CAR hardware and the **6-byte
EXA protocol**, starting with read-only checks and able to supervise control trials
locally. This is not an official Immergas product, Magis Modbus integration or a
replacement for boiler safety functions. Other installations are not yet validated.

## Backend features

- Local temperatures, targets, operating mode, modulation and reported activity/flame.
- Explicit CAR/HA handoff, OFF/Summer/Winter modes and water settings.
- One room target using CAR measurement; room-target writes are enabled
  separately, never automatically.
- Both water settings can be saved under HA ownership in OFF. DHW in OFF is saved
  only in HA and applied after the next explicit Summer/Winter selection. Saving
  other integration options preserves this pending target.
- Control permissions default to disabled. A new confirmed HA choice saves control
  intent; after reconnection/restart the integration attempts to restore it and known
  water targets. This can restart heating/DHW. Without saved intent it does not take
  ownership. Selecting CAR cancels recovery; foreign sessions, active local CAR,
  timers, missing permissions or invalid inputs block it. An uncertain write blocks
  recovery across restarts until the state is inspected and a new deliberate user
  choice is made.

Summer permits DHW only; Winter permits heating and DHW. Changing a limit never
selects a mode. Physical CAR may remain locally OFF while providing temperature in
the verified HA-owned setup; this is not a global boiler OFF or proof of all fallback
cases. The only dashboard included is an optional native YAML example with placeholder
IDs, not a private dashboard, screenshot or household entity mapping.

## Known limitations

- Operational evidence is limited to one installation, historically HA 2026.10.1;
  it does not establish compatibility with all HA versions or hardware models.
- Long-term stability, all network/power failure cases and subsequent independent
  heating from physical CAR with HA unavailable have not been validated.
- Invalid inputs stop further writes, not necessarily the boiler. This is not a fail-safe.
- HA's persistent TCP session may prevent simultaneous official mobile-app access.
- Uncertain writes are not automatically retried; inspect the state before further action.
- Antifreeze, cooling, independent DHW-off and service/reset controls are not implemented.
- Telemetry is not independent proof of water flow, pump operation or heat output.
- This is not HACS default-catalog distribution or HA/Hassfest/HACS certification.

## Reporting problems

Include exact boiler/module/CAR models, HA and integration versions, expected and
actual behavior, and whether another app was active. Do not publish passwords, MACs,
IPs, identification frames, private configuration or screenshots with personal data.
