"""One shared poll; compensation is opt-in, explicitly armed and never takes over."""
from datetime import datetime, timedelta, timezone
import asyncio
import logging
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .client import DominusError, WriteUncertain, Snapshot
from .const import (CONF_COMPENSATION_WRITE, CONF_CONTROLS, CONF_INTERVAL,
                    CONF_ROOM_DESIRED, CONF_ROOM_SOURCE, DEFAULT_INTERVAL,
                    DEFAULT_ROOM_DESIRED, DOMAIN, ROOM_MIN, ROOM_MAX,
                    CONF_SOURCE_MAX_AGE, DEFAULT_SOURCE_MAX_AGE,
                    CONF_ROOM_SOURCE_UPSTAIRS, CONF_ROOM_SOURCE_MODE,
                    DEFAULT_ROOM_SOURCE_MODE, ROOM_SOURCE_MODES, RUNTIME_OPTIONS,
                    CONF_PENDING_DHW)
from .temperature_input import preview_compensated_target, preview_measurement


class DominusCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        self.entry, self.client = entry, client
        self.last_command_error = None
        self.command_in_progress = None
        self._confirmed = Snapshot({}, {})
        self._command_refresh_task = None
        self._refresh_requested = False
        self.compensation_error = None
        self.source_age_seconds = None
        self._writes_armed = False
        self._source_write_pending = False
        self.connection_options = {k: v for k, v in entry.options.items() if k not in RUNTIME_OPTIONS}
        self.interval = entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL)
        super().__init__(hass, logging.getLogger(__name__), config_entry=entry,
                         name=DOMAIN, update_interval=timedelta(seconds=self.interval))
        client.on_connection_lost = self._connection_lost

    def _connection_lost(self):
        self._writes_armed = False
        self.compensation_error = "Control lease lost; explicit takeover required"
        self.async_set_update_error(UpdateFailed("Dominus connection/control lease lost; no automatic takeover"))

    def _calculate(self, snapshot, now, source_mode=None):
        values = snapshot.values
        desired = self.entry.options.get(CONF_ROOM_DESIRED, DEFAULT_ROOM_DESIRED)
        values["desired_room_target"] = desired
        snapshot.observed["desired_room_target"] = now
        self.source_age_seconds = None
        # Cached snapshots can be recalculated for an immediate source selection.
        # Never retain the previous source's measurement/target on invalid input.
        for key in ("ha_room_temperature", "compensated_room_target"):
            values.pop(key, None)
            snapshot.observed.pop(key, None)
        mode = source_mode if source_mode is not None else self.entry.options.get(CONF_ROOM_SOURCE_MODE, DEFAULT_ROOM_SOURCE_MODE)
        values["room_source_mode"] = mode
        snapshot.observed["room_source_mode"] = now
        if mode not in ROOM_SOURCE_MODES:
            return "source_not_configured"
        if mode == "car":
            # Use this fresh device snapshot, not our previous HA sensor state.
            measured = preview_measurement({"car": values.get("room_temperature")}, "car")["candidate_celsius"]
            stamp = snapshot.observed.get("room_temperature")
            max_age = 2 * self.interval + 30
        else:
            key = CONF_ROOM_SOURCE_UPSTAIRS if mode == "upstairs" else CONF_ROOM_SOURCE
            source_id = self.entry.options.get(key)
            if not source_id:
                return "source_not_configured"
            source = self.hass.states.get(source_id)
            if source is None:
                return "source_unavailable"
            if source.attributes.get("unit_of_measurement") != "°C":
                return "source_requires_celsius"
            stamp = getattr(source, "last_reported", None) or getattr(source, "last_updated", None)
            max_age = self.entry.options.get(CONF_SOURCE_MAX_AGE, DEFAULT_SOURCE_MAX_AGE)
            measured = preview_measurement({source_id: source.state}, source_id)["candidate_celsius"]
        if stamp is None or stamp.tzinfo is None:
            return "source_stale"
        self.source_age_seconds = round((now - stamp).total_seconds(), 1)
        if not 0 <= self.source_age_seconds <= max_age:
            return "source_stale"
        if measured is None:
            return "source_unavailable"
        values["ha_room_temperature"] = measured
        snapshot.observed["ha_room_temperature"] = stamp
        result = preview_compensated_target(requested_celsius=desired,
                                           car_celsius=values.get("room_temperature"),
                                           ha_celsius=measured, target_min=ROOM_MIN, target_max=ROOM_MAX)
        candidate = result["candidate_target_celsius"]
        if candidate is None:
            return result["status"]
        values["compensated_room_target"] = desired if mode == "car" else candidate
        snapshot.observed["compensated_room_target"] = now
        return "simulation_ready"

    async def _async_update_data(self):
        try:
            snapshot = await self.client.read_snapshot()
        except DominusError as err:
            raise UpdateFailed(str(err)) from err
        self._overlay_confirmed(snapshot)
        now = datetime.now(timezone.utc)
        status = self._calculate(snapshot, now)
        if status != "simulation_ready" and self._writes_armed and self.entry.options.get(CONF_COMPENSATION_WRITE, False):
            self._writes_armed = False
            self.compensation_error = "Temperature input lost/invalid; inspect state and explicitly re-arm"
        if status == "simulation_ready" and self.entry.options.get(CONF_COMPENSATION_WRITE, False):
            if not self.entry.options.get(CONF_CONTROLS, False):
                status = "controls_disabled"
            elif not self._writes_armed or not self.client.owns_control:
                status = "explicit_takeover_required"
            elif self.compensation_error:
                status = "blocked_after_error"
            elif snapshot.values.get("mode") != "winter":
                status = "winter_required"
            else:
                candidate = snapshot.values["compensated_room_target"]
                current = snapshot.values.get("room_target")
                # Reduce write chatter. This is an explicit0.5°C output deadband,
                # not clipping or a claim of exact continuous error equivalence.
                exact_match = current is not None and round(candidate * 256) / 256 == current
                if exact_match or (current is not None and abs(candidate - current) < .5 and not self._source_write_pending):
                    status = "unchanged"
                    if exact_match:
                        self._source_write_pending = False
                else:
                    try:
                        await self.client.command("room_target", candidate)
                    except DominusError as err:
                        self.compensation_error = str(err)  # Latch: never repeat on the next poll.
                        status = "blocked_after_error"
                    else:
                        self._source_write_pending = False
                        snapshot.values["room_target"] = round(candidate * 256) / 256
                        snapshot.observed["room_target"] = datetime.now(timezone.utc)
                        status = "applied"
        snapshot.values["compensation_status"] = status
        snapshot.observed["compensation_status"] = datetime.now(timezone.utc)
        # An older in-flight poll must not undo a more recent verified command.
        self._overlay_confirmed(snapshot)
        return snapshot

    async def select_room_source(self, option):
        """Select immediately, independently of measurement age or device transport.

        Selection is configuration, not permission to regulate from invalid data.
        No TCP read/write, takeover or rearm belongs in this action.
        """
        if option not in ROOM_SOURCE_MODES:
            raise HomeAssistantError("Unknown room temperature source")
        key = CONF_ROOM_SOURCE_UPSTAIRS if option == "upstairs" else CONF_ROOM_SOURCE
        if option != "car" and not self.entry.options.get(key):
            raise HomeAssistantError("Room temperature source is not configured")
        changed = self.entry.options.get(CONF_ROOM_SOURCE_MODE, DEFAULT_ROOM_SOURCE_MODE) != option
        self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, CONF_ROOM_SOURCE_MODE: option})
        if changed:
            self._source_write_pending = True  # Next permitted Winter poll; never rearm.
        self.update_room_preview()

    def update_room_preview(self):
        """Publish local source/target edits without polling or writing the boiler."""
        if self.data is not None:
            preview = Snapshot(dict(self.data.values), dict(self.data.observed))
            now = datetime.now(timezone.utc)
            status = self._calculate(preview, now)
            live = self.entry.options.get(CONF_COMPENSATION_WRITE, False)
            if status != "simulation_ready" and live and self._writes_armed:
                self._writes_armed = False
                self.compensation_error = "Temperature input lost/invalid; inspect state and explicitly re-arm"
            if status == "simulation_ready" and live:
                if not self.entry.options.get(CONF_CONTROLS, False):
                    status = "controls_disabled"
                elif not self._writes_armed or not self.client.owns_control:
                    status = "explicit_takeover_required"
                elif self.compensation_error:
                    status = "blocked_after_error"
                elif preview.values.get("mode") != "winter":
                    status = "winter_required"
                else:
                    status = "source_change_pending"
            preview.values["compensation_status"] = status
            preview.observed["compensation_status"] = now
            self.data = preview
            # Do not mark failed transport healthy or postpone the normal poll.
            self.async_update_listeners()

    @property
    def pending_dhw_target(self):
        """A saved request, never a fabricated device readback."""
        value = self.entry.options.get(CONF_PENDING_DHW)
        return value if type(value) is int and 10 <= value <= 60 else None

    def _clear_pending_dhw(self):
        if CONF_PENDING_DHW in self.entry.options:
            options = dict(self.entry.options)
            options.pop(CONF_PENDING_DHW)
            self.hass.config_entries.async_update_entry(self.entry, options=options)

    async def set_dhw_target(self, value):
        """Save in OFF without I/O; active-mode changes keep fresh client guards."""
        data = self.data.values if self.data is not None else {}
        if (not self.last_update_success or not self.client.allow_controls
                or not self.client.allow_gas_dhw or not self.client.owns_control
                or data.get("mode") not in {"off", "summer", "winter"}):
            raise HomeAssistantError("DHW settings require available HA-owned control")
        if self.command_in_progress is not None:
            raise HomeAssistantError("A control change is already in progress")
        lo, hi = data.get("dhw_min"), data.get("dhw_max")
        if (type(value) is not int or not 10 <= value <= 60
                or lo is None or hi is None or not lo <= value <= hi):
            raise HomeAssistantError("DHW target is outside available device bounds")
        if data["mode"] == "off":
            self.hass.config_entries.async_update_entry(
                self.entry, options={**self.entry.options, CONF_PENDING_DHW: value})
            self.async_update_listeners()
            return  # No mode change, network request, refresh or automatic timer.
        # An explicit active-mode edit supersedes an older saved OFF request.
        # Consume before I/O: failure must not leave a hidden automatic retry.
        self._clear_pending_dhw()
        await self.command("dhw_target", value)

    def _accept_confirmed(self, confirmed):
        self._confirmed.values.update(confirmed.values)
        self._confirmed.observed.update(confirmed.observed)
        if self.data is not None:
            merged = Snapshot(dict(self.data.values), dict(self.data.observed))
            self._overlay_confirmed(merged)
            self.data = merged  # Unrelated values retain their original timestamps.

    def _overlay_confirmed(self, snapshot):
        for key, stamp in self._confirmed.observed.items():
            previous = snapshot.observed.get(key)
            if previous is None or stamp > previous:
                snapshot.values[key] = self._confirmed.values[key]
                snapshot.observed[key] = stamp

    def _queue_command_refresh(self):
        """Coalesce diagnostic follow-ups; entry unload cancels the background task."""
        self._refresh_requested = True
        if self._command_refresh_task is None or self._command_refresh_task.done():
            self._command_refresh_task = self.entry.async_create_background_task(
                self.hass, self._refresh_after_commands(), "dominus_post_command_refresh")

    async def _refresh_after_commands(self):
        while self._refresh_requested:
            self._refresh_requested = False
            await self.async_request_refresh()

    async def command(self, action, value=None):
        if self.command_in_progress is not None:
            raise HomeAssistantError("A control change is already in progress")
        self.command_in_progress = value if action == "panel_mode" else action
        self.async_update_listeners()
        try:
            if action == "panel_mode":
                confirmed = await self.client.set_panel_mode(value)
            else:
                confirmed = await self.client.command(action, value)
            requested_mode = value if action == "panel_mode" else action
            pending = self.pending_dhw_target
            if requested_mode in {"summer", "winter"} and pending is not None:
                # Keep the verified mode even if the subsequent saved TUV write fails.
                self._accept_confirmed(confirmed)
                if confirmed.values.get("mode") != requested_mode:
                    raise DominusError("Active mode was not confirmed; saved DHW not sent")
                self._clear_pending_dhw()
                confirmed = await self.client.command("dhw_target", pending)
            self.last_command_error = None
            if action in {"take", "release", "panel_mode"}:
                self.compensation_error = None
                self._writes_armed = self.client.owns_control and (action == "take" or (action == "panel_mode" and value != "local"))
            self._accept_confirmed(confirmed)
            self._queue_command_refresh()
        except DominusError as err:
            self.last_command_error = str(err)
            if isinstance(err, WriteUncertain):
                self.compensation_error = str(err)
                self._writes_armed = False
            self._queue_command_refresh()  # Expose partial/uncertain outcomes, without delaying the error.
            raise HomeAssistantError(str(err)) from err
        except asyncio.CancelledError:
            self._writes_armed = False
            self.compensation_error = "Control action interrupted; inspect state before explicit takeover"
            raise
        finally:
            self.command_in_progress = None
            self.async_update_listeners()
