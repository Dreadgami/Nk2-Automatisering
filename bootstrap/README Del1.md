# Bootstrap: SSH-oppsett via konsoll (Del 1)

Scriptet `bootstrap_ssh.py` setter opp grunnkonfigurasjonen på en Cisco-ruter og/eller -switch over konsollkabelen, med Python og `pyserial`. Dette sparer tid ved å konfigurere hostname, IP, SSH osv.

Dette trengs før Ansible (Del 2). Hvis Ansible kjøres med en gang på en enhet uten grunnkonfigurasjon, får man *day 0-problemet*: Ansible har ingen måte å koble seg på enheten, fordi den kobler seg til over SSH.

## Krav

- Python 3.10 eller nyere
- `pyserial`
- PC med serieport (DB9) eller USB-til-seriell-adapter
- Cisco konsollkabel (RJ45 til DB9)

Testet mot:

| Enhet | OS |
|---|---|
| ISR 4221 | IOS-XE |
| Catalyst 3650 | IOS-XE |
| Catalyst 2960 | IOS |

## Installasjon

```powershell
git clone https://github.com/Dreadgami/Nk2-Automatisering.git
cd Nk2-Automatisering
python -m venv venv
venv\Scripts\Activate.ps1        # Linux: source venv/bin/activate
pip install pyserial
```

Hvis PowerShell blokkerer aktiveringen:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Koble til enheten

1. Koble konsollkabelen fra PC-en til **console**-porten på enheten.
2. Finn riktig COM-port:
   ```powershell
   python -m serial.tools.list_ports -v
   ```
   Du kan også dobbeltsjekke porten i Device Manager (Enhetsbehandling).
   Se etter "Communications Port" eller en USB-seriell-adapter. Porter merket "Bluetooth" eller "Intel Active Management Technology - SOL" er ikke konsollporten.
3. På Linux heter portene typisk `/dev/ttyS0` (innebygd) eller `/dev/ttyUSB0` (USB-adapter).
4. **Lukk PuTTY eller andre terminalprogrammer.** Bare ett program kan bruke porten om gangen.

Seriell-innstillinger: 9600 baud, 8 databit, ingen paritet, 1 stoppbit (8N1).

## Bruk

```powershell
python bootstrap\bootstrap_ssh.py
```

Scriptet spør om følgende:

| Felt | Eksempel | Merknad |
|---|---|---|
| COM-port | `COM1` | |
| Enhetstype | `switch` / `router` | Avgjør hvilke kommandoer som sendes |
| Hostname | `SW1` | |
| Domenenavn | `lab.local` | Kreves for å lage RSA-nøkkel |
| Brukernavn | `admin` | Lokal bruker for SSH |
| Passord | | Skjult input |
| Enable secret | | Skjult input |
| Mgmt-interface | `vlan 56` / `g0/0/0` | SVI på switch, fysisk port på ruter |
| Mgmt-IP og maske | `192.168.56.2` `255.255.255.0` | Valideres |
| Default gateway | `192.168.56.1` | Kun switch |

### Hva som konfigureres

- hostname og domenenavn
- enable secret og lokal bruker (privilege 15)
- RSA-nøkkel (2048 bit) og SSH versjon 2
- IP-adresse på management-interface
- default gateway (kun switch)
- vty 0–4: `login local` og `transport input ssh`
- lagring med `write memory`

## Verifisering

På enheten:

```
show ip ssh
show ip interface brief
```

`show ip ssh` skal vise *SSH Enabled – version 2.0*.

Fra en PC i samme subnett:

```powershell
ping 192.168.56.10
ssh admin@192.168.56.10
```

## Designvalg

- **Ingen hardkodede verdier.** Brukeren skriver inn verdiene selv, slik at de blir riktige for hver enhet og scriptet kan brukes på forskjellige enheter enkelt og smidig. Dette syns jeg er den viktigste funksjonen i scriptet, nettopp på grunn av fleksibiliteten.
- **Passord vises ikke.** Passordene leses med `getpass` og skjules i utskriften. De kan ikke vises, for hvis utskriften blir delt på GitHub, sendt på e-post eller kopiert, ligger passordet der ute for alle.
- **Validering av input.** Tomme svar avvises, og IP-adresser og masker sjekkes med `ipaddress`-modulen før noe sendes til enheten.
- **Robust oppkobling.** `prepare_device()` håndterer flere tilstander: initial configuration dialog, autoinstall, `>`-prompt, config-modus og enheter som allerede har enable secret, noe som gjør scriptet fleksibelt og brukervennlig.
- **Loggmeldinger filtreres.** IOS-XE sender syslog-meldinger (starter med `*`) som kan komme etter prompten. `last_line()` ser bort fra dem.
- **Feildeteksjon.** Svar fra enheten sjekkes mot kjente IOS-feilmeldinger (`% Invalid`, `% Incomplete` osv.).

## Erfaringer fra testing

### Scriptet avsluttet uten å gjøre noe

- **Problem:** Scriptet avsluttet med en gang, uten å spørre om noe.
- **Årsak:** Jeg sjekket slutten av fila med `Get-Content -Tail` og så at `if __name__ == "__main__":` og `main()` manglet. Python definerte bare funksjonene, men kalte aldri `main()`.
- **Løsning:** La til kallet nederst i fila.

### `ip domain-name` feilet på 4221

- **Problem:** Kommandoen ble avvist med `% Invalid input`.
- **Årsak:** IOS-XE godtar bare `ip domain name`, med mellomrom. Følgefeil: uten domenenavn ble ingen RSA-nøkkel laget, men scriptet oppdaget ikke den feilen først.
- **Løsning:** Ny kommando og bredere feilsjekk med `ERROR_PATTERNS`.

### Feilsjekken ga falsk alarm

- **Problem:** Scriptet meldte FEIL på `crypto key generate`, selv om nøkkelen ble laget.
- **Årsak:** Sjekken `"%" in output` slo til på infomeldinger som `% The key modulus size is 2048 bits`.
- **Løsning:** Sjekke konkrete feilmeldinger i stedet.

### Scriptet kjørt mot feil enhet

- **Problem:** `interface vlan` feilet, og resten av kommandoene ble følgefeil.
- **Årsak:** Kabelen sto fortsatt i ruteren, men jeg valgte `switch` fordi jeg skrev for fort. Da `interface vlan` feilet, tok `exit` meg helt ut av config-modus. Ruteren ble lagret som `SW1`. Jeg oppdaget det rett etterpå.
- **Erfaring:** Én feil kan gi mange følgefeil. En mulig forbedring er å sjekke enhetstypen automatisk.

### Loggmeldinger skjulte prompten (3650)

- **Problem:** Scriptet skrev "Fikk ikke kontakt med enheten" mot 3650-en.
- **Årsak:** Jeg la inn en debug-utskrift og så at `Switch>` faktisk kom, men ble etterfulgt av PnP- og CRYPTO-loggmeldinger. Teksten sluttet derfor ikke på `>`, og `endswith(">")` slo aldri til.
- **Løsning:** `last_line()` filtrerer bort linjer som starter med `*`, og antall forsøk ble økt fra 10 til 20.

### Enable secret fra en tidligere kjøring

- **Problem:** Ved andre kjøring svarte switchen `Password:`, og det ble `% Bad secrets` i loop.
- **Årsak:** Scriptet sendte bare Enter på passordspørsmålet.
- **Løsning:** `prepare_device()` sjekker svaret på `enable` med en gang og sender enable secret.

Feilen som tok lengst tid å finne, var at 3650-en ikke kom til enable-modus. Den krevde debug-utskrift og to rettinger: først loggmeldingene, så enable secret fra forrige kjøring.

## Feilsøking

| Problem | Årsak / løsning |
|---|---|
| "Klarte ikke å åpne COMx" | Feil port, eller PuTTY står åpen |
| "Fikk ikke kontakt med enheten" | Sett `DEBUG = True` øverst i scriptet for å se hva enheten svarer |
| `% Invalid input` på `ip domain-name` | Nyere IOS-XE bruker `ip domain name` (scriptet bruker dette) |
| Enheten avviser enable secret | Enheten er konfigurert fra før med et annet passord – slett konfig eller kjør password recovery |
| SVI står som `down` | VLAN-et må finnes og minst én port i VLAN-et må være aktiv |

## Begrensninger og videre arbeid

- Bruker faste ventetider (`time.sleep`) i stedet for å lese til prompten dukker opp.
- Oppretter ikke mgmt-VLAN eller access-port på switch.
- Kan ikke bytte enable secret på en enhet uten å kjenne det gamle. Hvis jeg skulle laget scriptet på nytt, ville jeg funnet en måte å bytte enable secret på.
