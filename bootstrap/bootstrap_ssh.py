"""
Bootstrap-script: setter opp SSH på Cisco switch/ruter via konsoll (pyserial).
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

def ask(prompt, secret=False):
    """Spør til brukeren gir et svar som ikke er tomt."""
    while True:
        answer = getpass(prompt) if secret else input(prompt)
        if answer.strip():
            return answer.strip()
        print("Feltet kan ikke være tomt, prøv igjen.")


def ask_ip(prompt):
    """Spør til brukeren gir en gyldig IPv4-adresse."""
    while True:
        answer = ask(prompt)
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

    # Grunnoppsett
    cfg["hostname"] = ask("Hostname: ")
    cfg["domain"] = ask("Domenenavn (f.eks. lab.local): ")

    # Innlogging
    cfg["username"] = ask("Brukernavn for SSH: ")
    cfg["password"] = ask("Passord for SSH-bruker: ", secret=True)
    cfg["enable_secret"] = ask("Enable secret: ", secret=True)

    # Management-adresse (switch bruker SVI, ruter bruker fysisk interface)
    if cfg["device_type"] == "switch":
        cfg["mgmt_interface"] = ask("Management-interface (f.eks. vlan 99): ")
    else:
        cfg["mgmt_interface"] = ask("Management-interface (f.eks. g0/0/0): ")
    cfg["mgmt_ip"] = ask_ip("Management-IP: ")
    cfg["mgmt_mask"] = ask_mask("Subnettmaske: ")

    # Default gateway trengs bare på switch (ruteren har rutetabell)
    if cfg["device_type"] == "switch":
        cfg["gateway"] = ask_ip("Default gateway: ")

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

    # Management-interface
    commands += [
        f"interface {cfg['mgmt_interface']}",
        f"ip address {cfg['mgmt_ip']} {cfg['mgmt_mask']}",
        "no shutdown",
        "exit",
    ]

    # Switch-spesifikt: default gateway (switchen ruter ikke selv)
    if cfg["device_type"] == "switch":
        commands.append(f"ip default-gateway {cfg['gateway']}")

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