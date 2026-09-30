"""
Bootstrap-script: setter opp SSH på Cisco switch/ruter via konsoll (pyserial).
"""
import serial
import time
from getpass import getpass


def get_user_input():
    """Spør brukeren om alt som ikke skal være hardkodet. Returnerer en dict."""
    # TODO: port, enhetstype (switch/router), hostname, domene,
    #       brukernavn, passord (getpass!), mgmt-interface, IP, maske,
    #       default gateway (bare switch)
    pass


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
    # TODO: felles kommandoer (hostname, domain, crypto key, bruker, vty, ssh v2)
    #       + switch-spesifikt (SVI + default-gateway)
    #       + ruter-spesifikt (fysisk interface med IP)
    pass


def main():
    cfg = get_user_input()
    ser = serial.Serial(port=cfg["port"], baudrate=9600, timeout=1)
    prepare_device(ser)
    for cmd in build_commands(cfg):
        print(send_command(ser, cmd))
    # TODO: lagre konfigurasjonen
    ser.close()


if __name__ == "__main__":
    main()