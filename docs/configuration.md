# Configuration, controls and safety

[Back to README](../README.md) · [Getting started](getting-started.en.md) · [Česky](getting-started.cs.md)

This guide describes current `main`, including changes after release v0.1.1.
The documented beta workflow uses **CAR as the room-temperature source**. It is
operating documentation, not an instruction to test an unattended boiler.

## Initial configuration

Install the component using the [network and first-use guide](getting-started.en.md).
Initial validation reads the device; it does not take ownership or select a mode.

The following permissions are separate and **disabled by default**:

- **Allow controls**: explicit ownership, mode and supported target changes.
- **Allow gas DHW**: required for Summer/Winter and DHW target changes.
- **Allow compensated target writes**: permits room-target writes after commissioning.
  With CAR selected as the measurement source, the requested target is forwarded
  unchanged; this permission does not introduce a replacement PID.

Changing connection/control options while HA owns the session is blocked: select
OFF and return control to CAR first. Editing the desired room target or saving a
DHW request in OFF does not reload or close the session.

Polling defaults to **60 seconds** (configurable 30–300). Device telemetry freshness
is `2 × polling interval + 30 seconds`. Missing or invalid data is not replaced by zero.

## Ownership and operating modes

Select **HA control in OFF** before enabling a mode. An active foreign session is
not adopted. Selecting CAR through the panel first sends OFF, then releases control;
it does not restore a previous CAR program.

| Mode | Permitted operation |
| --- | --- |
| OFF | No requested heating; water settings remain editable under HA ownership. |
| Summer | Gas DHW only, not radiator heating. |
| Winter | Radiator heating and gas DHW. |

A new mode is displayed as confirmed only after its independent device readback.
Commands may wait for a poll already using the shared connection. Pending commands
block simultaneous control changes. Failed/uncertain writes are not blindly retried.

### Remembering the last HA / CAR choice

A successful new HA ownership/panel choice saves the confirmed operating mode and
known heating-water/DHW targets locally in the config entry (`restore_control`).
Later confirmed mode/water edits update that request. The desired room target and
measurement-source choice already persist independently. Existing installations
without this saved choice do **not** infer permission from old telemetry: select HA
explicitly once after installing this change.

After a lost connection or HA restart/reload, a successful complete poll attempts
to restore the saved HA choice. Recovery takes ownership in OFF, restores the known
water limit, then the chosen mode and previously confirmed active DHW target.
With room-target writes enabled, Winter additionally requires valid recent input;
normal compensation then applies the current saved desired room target. Recovery
can start heating/DHW, briefly at a previous target during the mode transition.

Selecting CAR cancels the saved HA request **before** device I/O, even if that
release fails. Actual device state and saved intent remain distinct; no requested
value is fabricated as a readback. The compensation/measurement sensor attributes
`requested_control` and `control_restore_status` expose intent and recovery status.

Recovery is attempted at polling cadence, not in a tight retry loop. It waits when
controls/gas permission is missing, a timer is active, another client owns control,
local CAR is in an active mode, or required temperature input is invalid. It never
forces local CAR to OFF or steals another session. An uncertain restoration write
or cancellation persistently blocks automatic recovery, including after restart;
inspect the actual state and make a new deliberate ownership/panel choice.
Thus a brief read timeout no longer discards the user's selection, but this is not
an unconditional takeover or a guarantee of control during an outage.

## CAR measurement and the room target

Select **CAR** in the room measurement-source entity. This is separate from control
ownership: selecting the CAR temperature does **not** return control to physical CAR.
In the verified setup, physical CAR can remain in local OFF while supplying temperature
to HA-owned control. **Local CAR OFF is not global boiler OFF when HA controls it.**
Other models/wiring and all fallback cases have not been validated.

The desired-room number is local requested configuration. Changing it is immediate
and does not itself select a mode or take ownership. The reported controller target
is a separate, independently read value. A saved request is not proof of application.

Before enabling room-target writes, separately verify the existing native room
modulation and room-sensor settings (89/7 and 89/9). The integration does not silently
change them. Writes require this session's own lease, Winter, timer zero, valid recent
CAR data and an in-policy target of **5–35 °C**. Out-of-range results are rejected,
not clipped. Writes use F8.8 resolution and independent readback; an output threshold
limits unnecessary changes. Writing the target does not prove that CAR's own stored
program or internal target changes.

Invalid measurements disarm writes. Sensor recovery alone does not re-arm them;
inspect the state before deliberate control-owner action. No independent room zones
or guaranteed fallback are created by the integration.

## Water settings

Both controls are available in **OFF, Summer and Winter** only while HA owns control
and the relevant permissions, availability and device bounds are valid. CAR or
foreign ownership does not permit writes.

- **Maximum heating-water temperature** is an upper limit, not direct burner power.
  Changes use fresh device bounds within **20–85 °C**, including in OFF.
- **DHW target** uses whole degrees within **10–60 °C** and the device's bounds.
  Summer/Winter changes require a guarded write and independent READ56.
- In **OFF**, a DHW change is saved **only in HA**, without network I/O, mode changes
  or a heat request. The number exposes the requested value with `pending_value`,
  `reported_value` and `application_status`. Display it separately from the actual
  reported boiler target; saving locally is not a boiler confirmation.
- A saved DHW request survives restart and saving other integration options; it is
  applied only after the next **explicit
  Summer/Winter selection**, through either mode selector. Startup, polling,
  reconnect, takeover, OFF and CAR selection do not apply it. An active-mode edit
  supersedes an older saved request.
- Explicitly selecting Summer/Winter can start DHW heating, briefly at the previous
  target before the new write completes. The pending request is consumed before
  its single write attempt. On failure, the confirmed mode remains visible and the
  error is reported; no poll or later mode selection retries that request. Inspect
  the result and make a new explicit edit if necessary.

Saving a water setting never changes the operating mode. Direct low-level DHW
writes in OFF remain blocked because an ACK there did not establish application.
DHW minimum is **not** a separate DHW-off command.

## Connection and fallback limits

HA maintains **one persistent TCP session**, including in read-only mode, with a
read-only status heartbeat every 10 seconds. Releasing control to CAR does not
close that session; another client, including the official phone app, may be unable
to connect simultaneously.

A failed complete telemetry read may be retried once through a new identity-validated
connection. No partial snapshot is published. Losing an owned connection temporarily disarms
room-target writes. With a saved HA choice, startup, reload and reconnect use the
guarded restoration described above; without saved intent, they remain read-only.

**Stopping further writes is not a guaranteed boiler shutdown.** The last target
may remain effective. Closing HA closes transport without a hidden OFF command.
A controlled disconnect was verified in one installation with local CAR in OFF;
silent network/power failures, all other fallback cases and long-term stability
remain unvalidated. Subsequent manual heating from CAR with HA unavailable has not
been verified. Do not treat this integration as a safety interlock.

## Telemetry and dashboard example

The [optional dashboard example](../examples/dashboard.yaml) requires replacement
of its placeholder entity IDs. No dashboard is installed automatically and no private
installation's visual configuration or household mapping is shipped.

Flame, modulation and heating/DHW-active flags are reported telemetry, not independent
physical proof of water flow or pump operation. No dedicated boiler pump-running
entity is exposed. CAR temperature's `observed_at` records the successful device read,
including unchanged values, not the physical sensor's sampling time. Use it rather
than frontend-cached state timestamps when displaying CAR data age.

Antifreeze, cooling, independent DHW-off, service/reset and generic register writes
are not implemented. Do not expose TCP port
2000 publicly. Keep credentials, raw logs and private HA mappings outside Git.
