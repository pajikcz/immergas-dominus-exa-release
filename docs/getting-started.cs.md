# První zprovoznění v domácí síti

[English](getting-started.en.md) · [README](../README.md) · [Ovládání a bezpečnost](configuration.md)

Integrace je neoficiální a experimentální. Následující postup nejprve zprovozní
**pouze čtení**; instalace není povel k zapnutí kotle.

## 1. Ověřte zařízení

Potřebujete funkční modul Dominus s **6bajtovým protokolem EXA** a odpovídající
kotel/regulátor. Stejná značka ani název Dominus nezaručují kompatibilitu všech
modelů. Tato integrace není implementací Magis Modbus a nepodporuje automaticky
všechny výrobky Immergas. Poznamenejte si přesný model kotle, modulu a CAR.

Instalace v návodu předpokládá již odborně zapojený modul a CAR. Kvůli této
integraci nic nepřepojujte, nevyměňujte sondy a neměňte servisní parametry.

## 2. Nejprve oficiální mobilní aplikace

Ideálně nainstalujte oficiální aplikaci **Dominus** a podle návodu výrobce přes ni
modul připojte k domácí Wi-Fi. Ověřte, že aplikace správně zobrazuje vaše zařízení.
Názvy obrazovek se mohou lišit podle verze aplikace a platformy.

V seznamu zařízení hledejte informace nebo úpravu zvoleného zařízení:

- **MAC / identifikace Dominusu** — opište identitu tohoto modulu, ne telefonu či CAR.
- **Heslo zařízení / vzdáleného přístupu k zařízení** — podle verze může být v
  úpravě zařízení pouze maskované. Nepředpokládejte, že aplikace umí původní heslo
  odhalit; použijte známé heslo nastavené pro tento modul.
- **Lokální IP adresa**, pokud ji aplikace u zařízení dostupného v LAN zobrazuje.

Heslo zařízení nezaměňujte s heslem účtu aplikace, Wi-Fi nebo Home Assistantu.
Nevíte-li, které heslo bylo nastaveno, ověřte postup u výrobce/instalatéra;
**nedělejte kvůli zjištění údajů tovární reset ani změnu zapojení**.
Do veřejného issue neposílejte hesla, MAC, identifikační odpovědi ani snímek
obrazovky s osobními údaji.

## 3. Najděte lokální IP adresu modulu

V administraci routeru otevřete seznam připojených zařízení nebo DHCP pronájmů.
Najděte **modul Dominus**, nikoli samotný CAR, mobil nebo Home Assistant.
Použijte údaje z aplikace a routeru k ověření správného zařízení. Pokud se identity
liší, nepřebírejte náhodnou MAC; nejprve rozdíl vyjasněte.

Doporučuje se rezervace stejné adresy v DHCP, aby se IP po restartu nezměnila.
Router ani síť kvůli instalaci nemusíte resetovat. Ve veřejných příkladech
`DOMINUS_IP` znamená vaši vlastní adresu; nenahrazujte ji adresou jiného uživatele.

## 4. Ověřte síťovou cestu z HA

Home Assistant musí dosáhnout na lokální adresu Dominusu přes **TCP port 2000**.
Stejná domácí síť je nejjednodušší; při VLAN/oddělených sítích musí být povolena
odpovídající komunikace. Dosažitelnost z telefonu ještě nedokazuje dosažitelnost
z hostitele/kontejneru HA. Úspěšný ping sám nepotvrzuje funkční protokol.

Nepřesměrovávejte port 2000 do internetu, nevypínejte firewall a nepoužívejte
veřejnou WAN adresu. Port 2000 není webová stránka k otevření v prohlížeči.
Pro tuto instalaci není potřeba Home Assistant cloud token.

Po získání údajů aplikaci Dominus ukončete, včetně aktivního běhu na pozadí.
Klienti mohou soutěžit o jediné spojení. HA navíc drží spojení i v režimu pouze
čtení, takže pozdější souběžné připojení mobilní aplikace nemusí být možné.

## 5. Ruční instalace integrace

1. Použijte obsah **schválené vydané verze**, ne náhodný archiv ani složku výzkumu.
   Tento návod sám neoznamuje dostupnost veřejného vydání.
2. Zkopírujte složku `custom_components/immergas_dominus_exa` do adresáře
   `/config/custom_components/` vaší instalace HA. Správně vznikne
   `/config/custom_components/immergas_dominus_exa/manifest.json`, ne vnořená
   druhá složka `custom_components`.
3. Proveďte plánovaný restart HA. Neplánujte jej uprostřed nehlídané zkoušky topení;
   restart může ovlivnit i jiné vaše integrace a automatizace.
4. Otevřete **Nastavení → Zařízení a služby → Přidat integraci → Immergas Dominus EXA**.
5. Zadejte lokální host/IP, MAC identitu modulu a port 2000. MAC má formát
   `AA:BB:CC:DD:EE:FF` — to je zástupný příklad, nikoli skutečná adresa zařízení.
   Volitelné pole hesla slouží ke kontrole odpovědi zařízení; pokud jej vyplníte,
   musí odpovídat tomuto zařízení. Nejde o cloudové přihlášení ani šifrování spojení.

Přidání integrace validuje spojení pouze čtením, nepřebírá řízení a netestuje ohřev.
Pokud formulář skončí chybou, nepokračujte zapínáním ovládacích oprávnění.

## 6. První kontrola — pouze čtení

V možnostech nechte **Allow controls**, **Allow gas DHW** a
**Allow compensated target writes** vypnuté; výchozí nastavení je vypnuté.

Porovnejte hlášený režim a dostupné teploty s kotlem/CAR. Zkontrolujte opakovanou
aktualizaci údajů. `unavailable` není nula a samotná dostupnost entity nedokazuje
fyzický průtok.

### Pokojové měření z CAR

Tento postup používá pro pokojové měření **CAR**. V entitě výběru pokojového zdroje
výslovně zvolte CAR. Při řízení přes HA může CAR v ověřeném zapojení zůstat v místním
OFF a dál poskytovat měření. To **neznamená vypnutí kotle**, pokud má řízení HA.
Výběr CAR jako měření také není předání řídicího vlastnictví na CAR.
Jiné modely/zapojení a výpadkové chování vyžadují vlastní ověření.

Není vyžadován náš dashboard ani další frontend doplněk. Chcete-li příklad,
[dashboard.yaml](../examples/dashboard.yaml) obsahuje pouze zástupná ID; nahraďte
je skutečně registrovanými entitami a nevkládejte privátní export do veřejného issue.

## 7. Ovládání až jako samostatný krok

Před povolením řízení si přečtěte [konfigurační a bezpečnostní návod](configuration.md).
Buďte u zařízení, použijte jeho běžný provozní OFF a ověřte stav na místě.
Následně povolte jen potřebná oprávnění a výslovně převezměte řízení do HA v OFF.
Teprve vlastní výslovnou volbou Léto/Zima můžete povolit ohřev.

**Léto dovoluje TUV, nikoli radiátory. Zima dovoluje topení i TUV.** Změna limitu
sama nemění režim; cíl TUV uložený při OFF čeká v HA na příští výslovnou volbu
Léto/Zima. Minimum TUV není samostatný zákaz ohřevu TUV.

Nastavení nativní pokojové regulace se nesmí měnit odhadem. Výpadkové chování není
univerzálně ověřené: zastavení zápisů HA nemusí znamenat vypnutí kotle. Připravte
si běžný místní způsob zastavení podle výrobce; neodpojujte napájení kvůli doběhům.

## Poslední volba HA / CAR po výpadku

Nová úspěšná volba HA se ukládá spolu s potvrzeným režimem a známými vodními cíli.
Po návratu spojení i restartu HA se integrace pokusí tuto volbu obnovit; může tím
znovu spustit topení/TUV. Po instalaci změny je nutná jedna výslovná volba HA,
staré odečty zařízení se za souhlas nepovažují. Ruční CAR obnovování zruší i při
neúspěšném odeslání povelu.

Obnova vyčká při cizí session, aktivním místním režimu CAR, časovači, chybějícím
oprávnění nebo neplatném teplotním vstupu pro regulaci. CAR automaticky nevypíná.
Nejistý zápis obnovu zablokuje i přes restart; je nutná kontrola skutečného stavu
a nová vědomá volba řízení/režimu. Přání a stav obnovy jsou v atributech senzoru
kompenzace `requested_control` / `control_restore_status`; nejde o potvrzení, že
HA ovládá kotel během výpadku. [Podrobnosti](configuration.md#remembering-the-last-ha--car-choice).

## Když se nelze připojit

| Projev | Co zkontrolovat bez zapínání topení |
| --- | --- |
| Chyba spojení | Aktuální DHCP adresu, síťovou cestu z HA, firewall a jiného aktivního klienta. |
| Chyba identity | MAC modulu z aplikace, správnou IP a případné heslo zařízení; ne heslo Wi-Fi/účtu. |
| Zařízení už existuje | Existující config entry pro stejnou MAC; nezakládat druhou kopii. |
| Aplikace po přidání HA nefunguje | Možný konflikt spojení; CAR volba sama TCP spojení HA nezavře. |
| Zamčené ovladače | Oprávnění, potvrzeného vlastníka, dostupnost dat a probíhající povel. |

Při přetrvávající chybě zapište verzi HA/integrace, modely zařízení a redigovanou
chybovou zprávu. Změna nastavení spojení při aktivním vlastnictví HA vyžaduje nejprve
OFF a předání CAR; nepřerušujte aktivní vytápění jen kvůli diagnostické zkoušce.
