# NK2 Arbeidskrav 2 – Automatisering (STUD1)

Automatisert oppsett av Cisco-utstyr i to steg:

1. **[Del 1 – Python via konsoll](bootstrap/README.md):** `bootstrap_ssh.py` gir en ny eller nullstilt enhet SSH og en management-IP over konsollkabel.
2. **[Del 2 – Ansible over SSH](ansible/README.md):** playbooks setter opp ruting, VLAN, trunker, EtherChannel, HSRP og DHCP.

Python får enheten på nett, og Ansible gjør selve konfigurasjonen.

## Utstyr (STUD1)

| Rolle | Enhet |
|---|---|
| MLS1 | Catalyst 3650 |
| R1 | Cisco 4221 |
| R2 | Cisco 2901 |
| SW3 | Catalyst 2960 |
| SW0 | Catalyst 1000 |

## Mappestruktur

```
bootstrap/     Del 1 – Python-script og README
ansible/       Del 2 – inventory, variabler, playbooks og README
docs/img/      skjermbilder brukt i README-ene
requirements.txt
```
