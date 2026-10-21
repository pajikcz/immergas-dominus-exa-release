# Getting started on your local network

[Česky](getting-started.cs.md) · [README](../README.md) · [Controls and safety](configuration.md)

This unofficial integration is experimental. Start with **read-only telemetry**;
installing it is not a request to turn the boiler on.

## 1. Check the hardware

You need a working Dominus module using the **6-byte EXA protocol** and a compatible
boiler/controller. The brand or Dominus name alone does not establish compatibility
with every model. This integration is not Magis Modbus. Record the exact boiler,
module and CAR model before reporting compatibility.

This guide assumes professionally installed, working equipment. Do not rewire CAR,
replace probes or change service parameters to try the integration.

## 2. Start with the official mobile app

Preferably install the official **Dominus** app and first connect the module to
your home Wi-Fi using the manufacturer's instructions. Verify that the app displays
the correct device. Screen names differ between app versions and platforms.

Look for the selected device's information/edit screen:

- **MAC / Dominus identity**: use this module's identity, not the phone or CAR.
- **Device / device remote-access password**: an edit screen may show only a masked
  field. Do not assume the app can reveal an existing password; use the known
  password configured for that module.
- **Local IP address**, if shown while the module is reachable on the LAN.

The device password is not your app account, Wi-Fi or Home Assistant password.
If you do not know which password was configured, check the manufacturer's or
installer's instructions. **Do not factory-reset or rewire equipment to obtain it.**
Do not share passwords, MACs, raw identification replies or screenshots containing
personal data in a public issue.

## 3. Find the module's local IP address

Open your router's connected-device or DHCP-lease list. Identify the **Dominus
module**, not CAR, the phone or HA. Cross-check the app and router information.
If the identities differ, investigate rather than entering an arbitrary MAC.

A DHCP reservation is recommended to keep the address stable. No router/network
reset is needed. `DOMINUS_IP` in instructions means your own module's address,
not an address copied from another installation.

## 4. Check the network path from HA

Home Assistant must reach the module's local address over **TCP port 2000**.
A shared LAN is simplest; VLANs/separate networks need an appropriate route and
firewall permission. Reachability from your phone does not establish reachability
from the HA host/container. Ping success alone is not a working protocol check.

Do not forward port 2000 to the internet, disable the firewall or enter a public
WAN address. Port 2000 is not a web page. An HA cloud token is not required.

After obtaining the settings, close the Dominus app, including active background
use. Clients may compete for one connection. HA keeps a connection even while
read-only, so subsequent simultaneous app access may be unavailable.

## 5. Install manually

1. Use the contents of an **approved release**, not an unrelated archive or research
   directory. This guide does not announce that a public release is available.
2. Copy `custom_components/immergas_dominus_exa` into HA's
   `/config/custom_components/`. The result must include
   `/config/custom_components/immergas_dominus_exa/manifest.json`, not an additional
   nested `custom_components` directory.
3. Perform a planned HA restart. Do not do this during an unattended heating trial;
   a restart can also affect your other integrations and automations.
4. Open **Settings → Devices & services → Add integration → Immergas Dominus EXA**.
5. Enter the LAN host/IP, module MAC and port 2000. The MAC format is
   `AA:BB:CC:DD:EE:FF`: this is a placeholder, not a device to contact.
   The optional password field checks the device's identification reply; if entered,
   it must match that device. It is not a cloud login or transport encryption.

Adding the integration validates the connection by reading only. It does not take
control or test heating. If the form fails, do not enable control permissions.

## 6. First checks: read-only

Leave **Allow controls**, **Allow gas DHW** and **Allow compensated target writes**
disabled; these are the defaults.

Compare the reported mode and available temperatures with the boiler/CAR. Check
that observations continue to update. `unavailable` is not zero; available telemetry
is not physical proof of water flow.

### CAR room measurement

This workflow uses **CAR** for room measurement: explicitly select CAR in the
room-source entity. In the verified wiring, physical CAR can remain in local OFF
while supplying temperature to HA-owned control. This **does not mean the boiler
is OFF** when HA controls it. Selecting CAR as a measurement is also not returning
control ownership to CAR. Other models/wiring and fallback behavior need their
own verification.

No private dashboard or additional frontend component is required. The optional
[dashboard example](../examples/dashboard.yaml) uses placeholder entity IDs: replace
them with registered entities, and do not attach a private export to public issues.

## 7. Enable control only as a separate step

Read the [configuration and safety guide](configuration.md) first. Be physically
present, use the equipment's normal operating OFF and verify its condition locally.
Then enable only the necessary permissions and explicitly take HA ownership in OFF.
Only your subsequent deliberate Summer/Winter selection can enable heating.

**Summer permits DHW, not radiators. Winter permits heating and DHW.** Changing a
limit never selects a mode. A DHW target saved in OFF remains in HA until your next
explicit Summer/Winter selection. The minimum DHW target is not a DHW-off command.

Do not guess native room-control settings. Outage behavior is not universally
validated: stopping HA writes may not stop the boiler. Know the manufacturer's
normal local stop procedure; do not cut power to interrupt required pump/fan run-on.

## Remembering HA / CAR after an outage

A successful new HA choice saves the confirmed mode and known water targets.
After reconnection or an HA restart, the integration attempts to restore that
choice; this can restart heating/DHW. Explicitly select HA once after installing
this change: old telemetry is not treated as permission. Selecting CAR cancels
recovery even if the release command fails.

Recovery waits for foreign sessions, active local CAR modes, timers, missing
permissions or invalid regulation inputs. It never forces local CAR to OFF.
An uncertain write blocks recovery across restarts until the actual state is
inspected and a new deliberate ownership/panel choice is made. Compensation sensor
attributes `requested_control` / `control_restore_status` distinguish intent from
actual control; HA cannot control the boiler during a real outage.
[Details](configuration.md#remembering-the-last-ha--car-choice).

## Troubleshooting without turning heating on

| Symptom | Check |
| --- | --- |
| Cannot connect | Current DHCP address, path from HA, firewall and another active client. |
| Identification failure | Module MAC from the app, correct IP and device password, not account/Wi-Fi credentials. |
| Device already configured | Existing config entry for the same MAC; do not create a duplicate. |
| Phone app stops connecting | Possible connection contention; selecting CAR alone does not close HA's TCP session. |
| Controls unavailable | Permissions, confirmed owner, available data and a command in progress. |

For persistent errors, record HA/integration versions, hardware models and a redacted
error message. Changing connection settings while HA owns control requires OFF and
release to CAR first. Do not interrupt active heating merely to try diagnostics.
