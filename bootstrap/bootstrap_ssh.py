"""
Bootstrap-script: setter opp SSH på Cisco switch/ruter via konsoll (pyserial).
Gir enheten akkurat nok konfig til at Ansible kan nå den over SSH.
"""
import serial
import time
import ipaddress
from getpass import getpass

# Sett til True for å se hva enheten svarer under tilkobling
DEBUG = False

# IOS-meldinger som betyr at en kommando feilet
ERROR_PATTERNS = [
    "% Invalid",
    "% Incomplete",
    "% Ambiguous",
    "% Unknown",
    "% Please",
]


# ---------- Input fra bruker ----------

def ask(prompt, secret=False, optional=False):
    """Spør brukeren. Tomt svar er bare lov når optional=True (returnerer da "")."""
    while True:
        answer = getpass(prompt) if secret else input(prompt)
        answer = answer.strip()
        if answer or optional:
            return answer
        print("Feltet kan ikke være tomt, prøv igjen.")


def ask_ip(prompt, optional=False):
    """Spør til brukeren gir en gyldig IPv4-adresse (eller tomt svar hvis optional)."""
    while True:
        answer = ask(prompt, optional=optional)
        if not answer:
            return ""
        try:
            ipaddress.IPv4Address(answer)
            return answer
        except ipaddress.AddressValueError:
            print("Ugyldig IP-adresse, prøv igjen.")


def ask_mask(prompt):
    """Spør til brukeren gir en gyldig subnettmaske."""
    while True:
        answer = ask(prompt)
        try:
            ipaddress.IPv4Network(f"0.0.0.0/{answer}")
            return answer
        except ValueError:
            print("Ugyldig subnettmaske, prøv igjen.")


def get_user_input():
    """Spør brukeren om alt som ikke skal være hardkodet. Returnerer en dict."""
    cfg = {}

    # Tilkobling
    cfg["port"] = ask("COM-port (f.eks. COM1): ")

    # Enhetstype: godta bare switch eller router
    while True:
        cfg["device_type"] = ask("Enhetstype (switch/router): ").lower()
        if cfg["device_type"] in ("switch", "router"):
            break
        print("Skriv enten 'switch' eller 'router'.")
    is_switch = cfg["device_type"] == "switch"

    # Grunnoppsett
    cfg["hostname"] = ask("Hostname: ")
    cfg["domain"] = ask("Domenenavn (f.eks. lab.local): ")

    # Innlogging
    cfg["username"] = ask("Brukernavn for SSH: ")
    cfg["password"] = ask("Passord for SSH-bruker: ", secret=True)
    cfg["enable_secret"] = ask("Enable secret: ", secret=True)

    # Management-interface
    # Switch: SVI (vlan X) eller routed port på multilayer-switch (g1/0/3)
    # Ruter: fysisk interface (g0/0/1 på 4221, g0/1 på 2901)
    while True:
        if is_switch:
            iface = ask("Management-interface (f.eks. vlan 10, eller g1/0/3 for routed port): ")
        else:
            iface = ask("Management-interface (f.eks. g0/0/1 eller g0/1): ")
        cfg["mgmt_vlan"] = ""
        if iface.lower().startswith("vlan"):
            vlan_id = iface.lower().replace("vlan", "").strip()
            if not vlan_id.isdigit():
                print("Skriv VLAN-interfacet som f.eks. 'vlan 10'.")
                continue
            cfg["mgmt_vlan"] = vlan_id
        cfg["mgmt_interface"] = iface
        break

    cfg["mgmt_ip"] = ask_ip("Management-IP: ")
    cfg["mgmt_mask"] = ask_mask("Subnettmaske: ")

    # Gateway: switch bruker default-gateway, ruter får en default route
    if is_switch:
        cfg["gateway"] = ask_ip("Default gateway (Enter for å hoppe over): ", optional=True)
    else:
        cfg["gateway"] = ask_ip("Default route next-hop (Enter for å hoppe over): ", optional=True)

    # Switch med SVI: hvilke porter som skal bære mgmt-VLAN-et
    cfg["access_ports"] = ""
    cfg["trunk_ports"] = ""
    if is_switch and cfg["mgmt_vlan"]:
        cfg["access_ports"] = ask(
            f"Access-porter i VLAN {cfg['mgmt_vlan']} (f.eks. fa0/3 - 4, Enter for ingen): ",
            optional=True)
        cfg["trunk_ports"] = ask(
            "Trunk-porter (f.eks. fa0/2, Enter for ingen): ", optional=True)

    return cfg


# ---------- Kommunikasjon med enheten ----------

def send_command(ser, command, wait=1):
    """Sender én kommando og returnerer det enheten svarte."""
    ser.write((command + "\r").encode())  # IOS forventer Enter (\r) etter hver kommando
    time.sleep(wait)                       # gi enheten tid til å svare
    output = ser.read(ser.in_waiting).decode(errors="ignore")
    return output


def last_line(output):
    """Returnerer siste linje som ikke er en loggmelding (de starter med *)."""
    lines = [line.strip() for line in output.splitlines()
             if line.strip() and not line.strip().startswith("*")]
    return lines[-1] if lines else ""


def prepare_device(ser, enable_secret):
    """Vekker enheten, hopper over initial dialog og går til privileged EXEC (#)."""
    for _ in range(20):  # IOS-XE er treg og bråkete etter boot, så vi gir den flere forsøk
        output = send_command(ser, "", wait=2)
        if DEBUG:
            print(f"[debug] {output!r}")
        prompt = last_line(output)

        if "initial configuration dialog" in output:
            send_command(ser, "no", wait=5)
        elif "terminate autoinstall" in output:
            send_command(ser, "yes", wait=5)
        elif "(config" in prompt:
            send_command(ser, "end")                # står i config-modus fra før
        elif prompt.endswith(">"):
            # Enheten kan ha enable secret fra en tidligere kjøring
            output = send_command(ser, "enable", wait=2)
            if "Password" in output:
                output = send_command(ser, enable_secret, wait=2)
                if "Bad secret" in output or "Access denied" in output:
                    print("Enheten avviste enable secret. Har den et annet passord fra før?")
                    return False
        elif prompt.endswith("#"):
            send_command(ser, "terminal length 0")  # slå av --More--
            return True

    return False


# ---------- Konfigurasjon ----------

def build_commands(cfg):
    """Lager kommandolisten ut fra enhetstype og input."""
    is_switch = cfg["device_type"] == "switch"
    commands = ["configure terminal"]

    # Felles for switch og ruter
    commands += [
        f"hostname {cfg['hostname']}",
        f"ip domain name {cfg['domain']}",
        f"enable secret {cfg['enable_secret']}",
        f"username {cfg['username']} privilege 15 secret {cfg['password']}",
        "crypto key generate rsa modulus 2048",
        "ip ssh version 2",
    ]

    # Switch med SVI: VLAN-et og portene må finnes før SVI-en kan komme opp
    if is_switch and cfg["mgmt_vlan"]:
        commands += [f"vlan {cfg['mgmt_vlan']}", "exit"]
        if cfg["access_ports"]:
            commands += [
                f"interface range {cfg['access_ports']}",
                "switchport mode access",
                f"switchport access vlan {cfg['mgmt_vlan']}",
                "no shutdown",
                "exit",
            ]
        if cfg["trunk_ports"]:
            commands += [
                f"interface range {cfg['trunk_ports']}",
                "switchport mode trunk",
                "no shutdown",
                "exit",
            ]

    # Management-interface
    commands.append(f"interface {cfg['mgmt_interface']}")
    if is_switch and not cfg["mgmt_vlan"]:
        commands.append("no switchport")  # routed port på multilayer-switch (3650)
    commands += [
        f"ip address {cfg['mgmt_ip']} {cfg['mgmt_mask']}",
        "no shutdown",
        "exit",
    ]

    # Gateway: switch -> default-gateway, ruter -> default route
    if cfg["gateway"]:
        if is_switch:
            commands.append(f"ip default-gateway {cfg['gateway']}")
        else:
            commands.append(f"ip route 0.0.0.0 0.0.0.0 {cfg['gateway']}")

    # VTY-linjer: kun SSH, logg inn med lokal bruker
    commands += [
        "line vty 0 4",
        "login local",
        "transport input ssh",
        "exit",
        "end",
    ]

    return commands


# ---------- Hovedprogram ----------

def main():
    cfg = get_user_input()

    try:
        ser = serial.Serial(port=cfg["port"], baudrate=9600, timeout=1)
    except serial.SerialException as e:
        print(f"Klarte ikke å åpne {cfg['port']}: {e}")
        return

    print("Kobler til enheten...")
    if not prepare_device(ser, cfg["enable_secret"]):
        print("Fikk ikke kontakt med enheten eller kom ikke til enable-modus.")
        print("Tips: sett DEBUG = True øverst i fila for å se hva enheten svarer.")
        ser.close()
        return

    for cmd in build_commands(cfg):
        # Skjul passord i det som vises på skjermen
        shown = "*** (kommando med passord skjult)" if "secret" in cmd else cmd
        print(f"> {shown}")

        # RSA-nøkkel tar tid, og kan spørre om å erstatte en eksisterende nøkkel
        if cmd.startswith("crypto key"):
            output = send_command(ser, cmd, wait=10)
            if "yes/no" in output:
                output = send_command(ser, "yes", wait=10)
        else:
            output = send_command(ser, cmd)

        # Sjekk om IOS avviste kommandoen
        if any(pattern in output for pattern in ERROR_PATTERNS):
            print(f"  FEIL: {output.strip()}")

    print("Lagrer konfigurasjon...")
    send_command(ser, "write memory", wait=5)
    ser.close()
    print("Ferdig! Test med: ssh <brukernavn>@<mgmt-ip>")


if __name__ == "__main__":
    main()