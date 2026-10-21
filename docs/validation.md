# Release candidate validation

Validated on 2026-10-21, using the development v0.2.0 backend.
These checks underpin v0.2.0-beta.1; they are not a certification.

- 96 offline unit tests passed; Python compilation passed.
- A clean local installation of Home Assistant Core 2026.10.1 on Python 3.14
  loaded this integration in a fresh temporary configuration directory.
- The real HA config flow created the entry using a synthetic device probe;
  all 36 integration entities loaded. The options form and its schema
  serialization succeeded. Control and gas-DHW permissions defaulted to disabled.
  Integration unload succeeded.
- Device probe and telemetry were simulated; device commands and outbound socket
  connections were blocked. No production HA or physical boiler was contacted.
  This verifies real HA integration loading, not live device interoperability,
  real browser interaction, HACS installation or physical recovery after outages.
- Hassfest and HACS Action have not been run. Long-term and physical outage
  behavior remains subject to the limitations in the configuration guide.

[Configuration and safety](configuration.md) · [Beta notes](releases/beta-draft.en.md)

## Česky

Dne 21. 10. 2026 prošlo 96 offline testů a kompilace. Čistý HA Core 2026.10.1
(Python 3.14) načetl integraci přes skutečný konfigurační tok, 36 entit,
formulář možností včetně serializace a následné odpojení. Ovládání i plynová
TUV byly výchozně nepovolené. Zařízení bylo simulované; povely a odchozí sockety
byly blokované. Nejde o fyzický test kotle, browser/HACS instalaci, Hassfest/HACS
certifikaci ani potvrzení chování při skutečném výpadku.
