"""
Bootstrap-script: setter opp SSH på Cisco switch/ruter via konsoll (pyserial).
"""
import serial
import time
from getpass import getpass


def ask(prompt, secret=False):
    """Spør til brukeren gir et svar som ikke er tomt."""
    while True:
        answer = getpass(prompt) if secret else input(prompt)
        if answer.strip():
            return answer.strip()
        print("Feltet kan ikke være tomt, prøv igjen.")


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
    cfg["mgmt_ip"] = ask("Management-IP: ")
    cfg["mgmt_mask"] = ask("Subnettmaske: ")

    # Default gateway trengs bare på switch (ruteren har rutetabell)
    if cfg["device_type"] == "switch":
        cfg["gateway"] = ask("Default gateway: ")

    return cfg


def send_command(ser, command, wait=1):
    """Sender én kommando og returnerer det enheten svarte."""
    ser.write((command + "\r").encode())  # IOS forventer Enter (\r) etter hver kommando
    time.sleep(wait)                       # gi enheten tid til å svare
    output = ser.read(ser.in_waiting).decode(errors="ignore")
    return output


def prepare_device(ser):
    """Vekker enheten, hopper over initial dialog og går til privileged EXEC (#)."""
    for _ in range(10):  # maks 10 forsøk, så scriptet ikke henger for alltid
        output = send_command(ser, "", wait=2)

        if "initial configuration dialog" in output:
            send_command(ser, "no", wait=5)
        elif "terminate autoinstall" in output:
            send_command(ser, "yes", wait=5)
        elif "(config" in output:
            send_command(ser, "end")          # står i config-modus fra før
        elif output.strip().endswith(">"):
            send_command(ser, "enable")
        elif output.strip().endswith("#"):
            send_command(ser, "terminal length 0")  # slå av --More--
            return True

    return False


def build_commands(cfg):
    """Lager kommandolisten ut fra enhetstype og input."""
    commands = ["configure terminal"]

    # Felles for switch og ruter
    commands += [
        f"hostname {cfg['hostname']}",
        f"ip domain-name {cfg['domain']}",
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


def main():
    cfg = get_user_input()

    try:
        ser = serial.Serial(port=cfg["port"], baudrate=9600, timeout=1)
    except serial.SerialException as e:
        print(f"Klarte ikke å åpne {cfg['port']}: {e}")
        return

    print("Kobler til enheten...")
    if not prepare_device(ser):
        print("Fikk ikke kontakt med enheten eller kom ikke til enable-modus.")
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

        # IOS markerer feil med %
        if "% Invalid" in output or "% Incomplete" in output:
            print(f"  FEIL: {output.strip()}")

    print("Lagrer konfigurasjon...")
    send_command(ser, "write memory", wait=5)
    ser.close()
    print("Ferdig! Test med: ssh <brukernavn>@<mgmt-ip>")

if __name__ == "__main__":
    main()