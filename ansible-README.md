# Del 2 – Ansible-konfigurasjon (STUD1)

Ansible logger inn på switchene og ruterne over SSH og setter opp VLAN, trunker, EtherChannel, HSRP og DHCP ut fra variabelfiler. Da slipper jeg å skrive kommandoene for hånd på hver enhet, og jeg kan kjøre samme oppsett på nytt, eller på et annet rack, bare ved å endre variablene.

## Sammenheng med Del 1 (Python)

Ansible trenger SSH for å komme inn på enhetene, men en ny eller nullstilt enhet har ikke SSH. Derfor gjør Python-scriptet i [`bootstrap/`](../bootstrap/README.md) «bootstrap»-jobben over konsollkabel: hostname, domene, RSA-nøkler, bruker, VTY med SSH og en management-IP. Når det er gjort, tar Ansible over og konfigurerer resten over nettverket. Python får enheten på nett, og Ansible gjør selve konfigurasjonen.

Koblingen mellom de to delene er management-IP-ene: adressen som gis i bootstrap-scriptet må være den samme som `ansible\\\_host` i [`inventory/hosts.yml`](inventory/hosts.yml). I tillegg gjør bootstrap-scriptet akkurat nok til at Ansible kan nå enhetene:

* **Rutere** får en default route opp mot multilayer-switchen, slik at svarene finner tilbake til MGMT-PC-en.
* **3650** får en routed port (`no switchport`) mot MGMT-PC-en.
* **Aksess-switcher** får mgmt-VLAN-et opprettet og opplinkene satt som trunk/access. Uten dette kan ikke Ansible nå dem, og da kan heller ikke Ansible sette det opp. Dette er delen av oppsettet som ikke kan gjøres med Ansible, og som derfor er løst i Python.

## Topologi og IP-plan

**Kabling**

|Fra|Til|
|-|-|
|MGMT-PC|MLS1 (3650) Gi1/0/3|
|MLS1 Gi1/0/1|R1 (4221) Gi0/0/1|
|MLS1 Gi1/0/2|R2 (2901) Gi0/1|
|R1 Gi0/0/0|SW3 (2960) Fa0/3|
|R2 Gi0/0|SW3 (2960) Fa0/4|
|SW3 Fa0/2|SW0 (Catalyst 1000) Gi1/0/3|
|SW0 Gi1/0/1|PC VLAN10\_1|
|SW0 Gi1/0/2|PC VLAN20\_2|
|SW0 Gi1/0/4–5|STUD2 Switch0 Gi1/0/4–5 (EtherChannel)|

**Subnett**

|Navn|Nettverks-ID|VLAN|Subnetmaske|Ledige adresser|Broadcast|Gateway|
|-|-|-|-|-|-|-|
|MGMT|172.16.99.0|–|255.255.255.248|.1–.6|172.16.99.7|.2 (MLS1)|
|MLS1–R1|172.16.2.0|–|255.255.255.252|.1–.2|172.16.2.3|–|
|MLS1–R2|172.16.2.4|–|255.255.255.252|.5–.6|172.16.2.7|–|
|VLAN 10|172.16.10.0|10|255.255.255.0|.1–.254|172.16.10.255|.254 (HSRP)|

**Enheter**

|Enhet|Interface|IP|Merknad|
|-|-|-|-|
|MGMT-PC|NIC|172.16.99.1/29|gw 172.16.99.2|
|MLS1|Gi1/0/3 / Gi1/0/1 / Gi1/0/2|.99.2 / .2.1 / .2.5|`ip routing`, statiske ruter til VLAN 10 via R1 og R2|
|R1|Gi0/0/1 / Gi0/0/0|.2.2 / .10.1|HSRP Active (prioritet 110), DHCP .20–.129|
|R2|Gi0/1 / Gi0/0|.2.6 / .10.2|HSRP Standby (prioritet 100), DHCP .130–.249|
|HSRP VIP|–|172.16.10.254|Gateway for VLAN 10|
|SW3|Vlan10|172.16.10.11|gw .254|
|SW0|Vlan10|172.16.10.12|gw .254|

To rutere deler ut adresser i samme VLAN, men fra hver sin del av nettet, slik at de aldri gir ut samme adresse.

## Struktur

```
ansible/
├── ansible.cfg              # peker på inventory, slår av host key checking i labben
├── ssh\\\_config\\\_legacy        # tillater gamle SSH-algoritmer for eldre IOS (se under)
├── inventory/
│   ├── hosts.yml            # hvilke enheter som finnes og hvilken IP de har
│   ├── group\\\_vars/          # det som er likt for en gruppe
│   │   ├── all.yml
│   │   ├── routers.yml
│   │   └── switches.yml
│   └── host\\\_vars/           # det som er unikt for en enhet
│       ├── MLS1.yml  R1.yml  R2.yml  SW3.yml  SW0.yml
└── playbooks/
    ├── 01\\\_mls.yml           # ruting på 3650
    ├── 02\\\_routers.yml       # LAN-interface, HSRP, DHCP
    ├── 03\\\_switches.yml      # VLAN, access, trunk, EtherChannel
    ├── site.yml             # kjører alle tre i riktig rekkefølge
    └── verify.yml           # show-kommandoer, endrer ingenting
```

* `inventory` sier hvilke enheter som finnes og hvilken IP de har.
* `group\\\_vars` er det som er likt for en gruppe, for eksempel brukernavn, `ansible\\\_network\\\_os: cisco.ios.ios` og VLAN-listen.
* `host\\\_vars` er det som er unikt for en enhet: porter, IP-er, HSRP-prioritet og DHCP-område.
* `playbooks` sier hva som skal gjøres. De inneholder logikk, ikke data.

Fordelen er at jeg bare endrer data, ikke kode. Kommer det et nytt VLAN, legger jeg det til i en fil. Byttes en port, endrer jeg det i den enhetens `host\\\_vars`. Playbookene blir ikke rørt. Det er samme tanke som en `.tfvars`-fil i Terraform.

Rekkefølgen i `site.yml` er viktig: MLS1 må konfigureres først (gjør ruterne nåbare), så ruterne (gjør switchene nåbare via HSRP-gatewayen), og til slutt switchene.

## Krav og installasjon

Ansible kjører ikke på Windows, så jeg brukte WSL (Ubuntu).

```bash
git clone https://github.com/Dreadgami/Nk2-Automatisering.git
cd Nk2-Automatisering
python3 -m venv venv
source venv/bin/activate
pip install ansible ansible-pylibssh
ansible-galaxy collection install cisco.ios
```

Ta i bruk SSH-innstillingene for eldre utstyr:

```bash
mkdir -p \\\~/.ssh
cp ansible/ssh\\\_config\\\_legacy \\\~/.ssh/config
chmod 600 \\\~/.ssh/config
```

Klon repoet i Linux-hjemmemappen, ikke under `/mnt/c/...`. Ansible ignorerer `ansible.cfg` i mapper som alle kan skrive til, og Windows-mapper ser slik ut fra WSL.

## Bruk

Fra `ansible/`-mappen, med venv aktivert:

```bash
ansible-playbook playbooks/site.yml -k -K        # hele oppsettet
ansible-playbook playbooks/02\\\_routers.yml -k -K  # bare en del
ansible-playbook playbooks/03\\\_switches.yml -k -K --limit SW0   # bare en enhet
ansible-playbook playbooks/verify.yml -k -K      # status, ingen endringer
```

`-k` spør om SSH-passordet og `-K` om enable secret. Passordene ligger ikke i repoet, fordi repoet er offentlig.

## Verifisering

<!-- Legg skjermbildene i docs/img/ med disse navnene -->

**Hele oppsettet kjørt med `site.yml`** – alle fem enheter, `failed=0`:

!\[Resultat av site.yml](../docs/img/site-recap.png)

**`verify.yml`** – alle enheter nås, ingen endringer:

!\[Resultat av verify.yml](../docs/img/verify-recap.png)

**DHCP og HSRP** – en PC på SW0 Gi1/0/1 fikk `172.16.10.131` (fra R2 sitt område), gateway `172.16.10.254` og domenet `lab.local`, og når gatewayen:

!\[DHCP-test](../docs/img/dhcp-test.png)

Når playbookene kjøres en gang til, viser oppgavene stort sett `ok` i stedet for `changed`. De er altså idempotente: de endrer bare det som avviker. Noen oppgaver viser alltid `changed`, fordi linjer som `no shutdown` og `spanning-tree portfast` ikke vises i `running-config` på samme form, så `ios\\\_config` sender dem på nytt. Det er ufarlig.

## Avtale med STUD2

|Tema|Avtale|
|-|-|
|VLAN 10|STUD1 sitt: 172.16.10.0/24, HSRP VIP `.254`, DHCP fra STUD1 sine rutere|
|VLAN 20|STUD2 sitt: 172.16.20.0/24, HSRP VIP `.254`, DHCP fra STUD2 sine rutere|
|EtherChannel|Gi1/0/4–5 på begge Switch0, LACP `mode active`, `channel-group 1`|
|Trunk over Po1|`allowed vlan 10,20`, `native vlan 999`|
|Kryss-PC-er|VLAN20\_2 står hos STUD1 (access 20), VLAN10\_2 hos STUD2 (access 10)|

## Status på EtherChannel

Min side er konfigurert med LACP i `mode active` på Gi1/0/4–5 på SW0, og Port-channel1 er satt opp som trunk. Partneren var ikke på labben, så den andre siden er ikke konfigurert. Derfor viser `show etherchannel summary` `Po1(SD)` og portene som `(D)` i stedet for `(SU)` og `(P)`. Det er forventet, ikke en feil hos meg. Fordi jeg bruker `active`, fungerer det uansett om partneren velger `active` eller `passive`, så lenge VLAN og trunk-innstillinger stemmer med det vi avtalte. Avtalen står over, så partneren kan kjøre sin del når som helst.

## Erfaringer fra testing

### `group\\\_vars` og `host\\\_vars` ble ikke lest

* **Problem:** `Connection type ssh is not valid for this module`.
* **Årsak:** Mappene lå i `ansible/`. `ansible-playbook` leser dem bare ved siden av inventory-fila eller playbooken, så `ansible\\\_connection: network\\\_cli` ble aldri lastet.
* **Løsning:** Flyttet dem inn i `inventory/`.

### SSH-algoritmer på gammelt utstyr

* **Problem:** Ansible fikk ikke koblet til 2901, 2960 og Catalyst 1000, selv om SSH var på.
* **Årsak:** Eldre IOS støtter bare gamle algoritmer, og SSH-biblioteket Ansible bruker (`libssh`) har slått dem av som standard. 2901 feilet på nøkkelutvekslingen (`diffie-hellman-group14-sha1`). 2960 krevde i tillegg `ssh-rsa`, CBC-kryptering (`aes128-cbc`) og `hmac-sha1`. Bytte til `paramiko` hjalp ikke, fordi nyere `paramiko` også har fjernet SHA-1.
* **Løsning:** `ssh\\\_config\\\_legacy` tillater de gamle algoritmene, **bare** for de tre gamle enhetene, med `KexAlgorithms +…`, `HostKeyAlgorithms +ssh-rsa`, `Ciphers +…` og `MACs +hmac-sha1`.
* **Lærdom:** Feilen satt i PC-en, ikke i switchen. Jeg leser SSH-feilmeldingen nøye før jeg begynner å endre på enheten.

### Passordet på SW3

* **Problem:** Verken SSH-passordet eller enable secret virket på SW3, selv om samme passord virket på alle andre enheter.
* **Årsak:** Passordet ble sannsynligvis feilskrevet da bootstrap-scriptet kjørte. `getpass` viser ikke hva man skriver og ba ikke om bekreftelse.
* **Løsning:** Password recovery på 2960 (`flash\\\_init`, `rename flash:config.text`) og ny bootstrap.

### Vlan1 hadde allerede en adresse i VLAN 10-nettet

* **Problem:** Etter recovery fikk SW3 ingen mgmt-IP, selv om bootstrap kjørte uten FEIL.
* **Årsak:** En blank 2960 har `ip address dhcp` på `Vlan1`. Portene mot ruterne lå i VLAN 1 før bootstrap, så switchen fikk `172.16.10.130` fra R2. Da nektet IOS å gi `Vlan10` en adresse i samme nett (`% 172.16.10.0 overlaps with Vlan1`), og scriptet fanget ikke opp den meldingen.
* **Løsning:** `no ip address` og `shutdown` på `Vlan1`.

### Rekkefølge ved EtherChannel-test

Jeg prøvde å teste EtherChannel mellom mine egne switcher (SW0 og SW3) mens partneren var borte. Jeg koblet kablene før SW3 var konfigurert, og mistet kontakten med SW3. Testen ble avbrutt og er ikke med i repoet. Lærdom: konfigurer begge sider før kabelen kobles.

## Videre arbeid

Med mer tid ville jeg ha:

* testet EtherChannel ferdig sammen med partneren
* delt opp playbookene i Ansible-roller (for eksempel `vlan`, `etherchannel`, `dhcp`)
* lagt passordene i Ansible Vault, slik at playbookene kan kjøres uten å spørre (i dag oppgis de med `-k`/`-K` og lagres ikke)
* utvidet `verify.yml` til å sjekke resultatet automatisk (for eksempel at R1 er HSRP Active), ikke bare vise det
* samlet Python og Ansible i ett startscript, slik at hele oppsettet kjøres med en kommando
* i bootstrap-scriptet: bekreftelse av passord, `overlaps` som feilmelding, og `Vlan1` slått av automatisk

