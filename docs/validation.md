# Release candidate validation

## v0.2.0-beta.2 candidate — 2026-11-09

Prepared locally, not published. Backend and tests match development commit
`991eb3ad2a52e6ab671f87fd2c8982c1e9a5861a`; only release manifest version and
public documentation/issue URLs differ. No experimental local WIP was imported.

- All **112 offline unit tests passed** (31.230 seconds, no skips).
- In a fresh temporary HA Core **2026.10.4 / Python 3.14.7** configuration, the
  real config flow created the entry, **34 entities** registered, the options
  form and its defaults validated, and integration unload succeeded.
- Both control and gas-DHW permissions were disabled by default.
- The same smoke procedure also loaded **34 entities in v0.2.0-beta.1**. The
  historical 36-entity count below is not a new candidate assertion; no entity
  platform/source files changed between these two versions.
- Device probe and telemetry were synthetic. Command methods and outbound
  connect/connect_ex/sendto were blocked. No production HA or boiler was contacted.
- Initial smoke-harness attempts needed a valid fixture MAC and HA registry
  initialization; these harness corrections did not change integration code.

These checks do **not** verify physical OFF, CAR selector position, hydraulic
flow, real outage/failover behavior, a complete house clone, browser/HACS
installation or long-term stability. Hassfest and HACS Actions have not run.
The explicit OFF path is covered by synthetic protocol/readback and interruption
regression tests, not new physical fault testing. No deployment was performed.

[Candidate notes](releases/v0.2.0-beta.2.en.md) · [Configuration and safety](configuration.md)

## Previous validation — v0.2.0-beta.1, 2026-10-21

The original report recorded 96 passing offline tests and a clean HA Core
2026.10.1 / Python 3.14 setup with synthetic probe/telemetry, config/options flow,
36 entities and unload. Commands and outgoing connections were blocked.
This is historical evidence, not a rerun of that environment or certification.

## Česky

Kandidát beta.2 není zveřejněný. Dne 9. 11. 2026 prošlo všech **112 offline testů**
bez přeskočení a čistý **HA Core 2026.10.4 / Python 3.14.7**: skutečný konfigurační
tok, **34 entit**, formulář možností s ověřenými výchozími hodnotami a odpojení.
Ovládání i plynová TUV byly výchozně zakázané. Stejný postup vytvořil 34 entit i
z původní beta.1; historický údaj 36 se na nový test nepřenáší. Před úspěšným
během bylo nutné opravit testovací MAC a inicializaci HA registrů v harnessu,
ne integraci.

Zařízení bylo simulované, povely i odchozí síť blokované. Nejde o fyzické ověření
vypnutí kotle, polohy CAR, průtoku nebo zotavení při výpadku, úplný klon domu,
browser/HACS instalaci ani Hassfest/HACS certifikaci. Produkce se neměnila.

[České poznámky kandidáta](releases/v0.2.0-beta.2.cs.md)
