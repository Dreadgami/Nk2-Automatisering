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
    # TODO: skriv kommandoen som bytes med "\r" på slutten,
    #       vent litt, les det som ligger i bufferet og returner det som tekst
    pass


def prepare_device(ser):
    """Vekker enheten, hopper over initial dialog og går til enable-modus."""
    # TODO: send tom linje, sjekk svaret:
    #   - "initial configuration dialog" -> svar "no"
    #   - prompt slutter på ">" -> send "enable"
    pass


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
    for cmd in build_commands(cfg):
        print(cmd)


if __name__ == "__main__":
    main()