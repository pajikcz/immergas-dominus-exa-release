# Experimentální beta — návrh poznámek k vydání

[English](beta-draft.en.md) · [První zprovoznění](../getting-started.cs.md)

**Pouze návrh ke schválení.** Nejde o zveřejněné vydání ani oznámení veřejné
dostupnosti. Verze/tag a licence dosud nejsou určeny pro veřejnou betu.

## Určení

Technicky zkušení uživatelé s odpovídajícím Dominus/CAR a **6bajtovým EXA**,
kteří nejprve ověří pouze čtení a mohou ovládání zkoušet pod místním dohledem.
Nejde o oficiální produkt Immergas, integraci Magis Modbus ani náhradu
bezpečnostních funkcí kotle. Kompatibilita s dalšími instalacemi není potvrzena.

## Funkce backendu

- Lokální teploty, cíle, režim, modulace a hlášená aktivita/plamen.
- Výslovné předání CAR/HA, režimy OFF/Léto/Zima a vodní limity.
- Jeden pokojový cíl s měřením z CAR; zápis pokojového cíle se povoluje
  samostatně, nikoli automaticky.
- Vodní nastavení lze uložit i v OFF při vlastním HA řízení. TUV v OFF se uloží
  pouze v HA a uplatní až po další výslovné volbě Léto/Zima. Uložení ostatních
  možností integrace tento čekající cíl zachová.
- Oprávnění jsou standardně vypnutá; při startu/reconnectu se nepřebírá řízení.

Léto dovoluje pouze TUV, Zima vytápění i TUV. Změna limitu sama nemění režim.
CAR může v ověřeném zapojení při řízení HA zůstat lokálně OFF a poskytovat měření;
nejde o globální OFF kotle ani důkaz všech výpadkových scénářů.
Součástí je pouze volitelný nativní YAML příklad dashboardu se zástupnými ID,
nikoli privátní dashboard, screenshoty či mapování domácnosti.

## Známá omezení

- Provozní ověření je omezené na jednu instalaci, historicky HA 2026.10.1;
  není to prohlášení kompatibility se všemi verzemi nebo modely.
- Neověřena dlouhodobá stabilita, všechny výpadky sítě/napájení ani následné
  samostatné vytápění fyzickým CAR při nedostupném HA.
- Neplatné vstupy zastaví další zápisy, ne nutně kotel. Nejde o fail-safe.
- Trvalé TCP spojení HA může blokovat souběžnou oficiální mobilní aplikaci.
- Po nejistém zápisu není automatický retry; kontrola stavu a další akce jsou ruční.
- Frýz, chlazení, samostatný zákaz TUV a servis/reset nejsou implementovány.
- Senzory nejsou nezávislým potvrzením průtoku, chodu čerpadla či výkonu.
- Nejde o vydání ve výchozím katalogu HACS ani o certifikaci HA/Hassfest/HACS.

## Hlášení problémů

Uveďte přesné modely kotle/modulu/CAR, verzi HA a integrace, očekávané a skutečné
chování a zda byla aktivní jiná aplikace. Nezveřejňujte hesla, MAC, IP,
identifikační rámce, privátní konfiguraci nebo screenshoty s osobními údaji.
