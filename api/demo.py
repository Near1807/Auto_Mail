"""Mode démo (``AUTOMAIL_DEMO=1``) : un faux Gmail pour essayer l'appli sans rien envoyer.

N'importe quel mot de passe est accepté sauf « faux ». Les adresses contenant
« bounce » sont refusées, pour voir à quoi ressemble une erreur.
"""

from __future__ import annotations

import imaplib
import smtplib
import time


class _Memory:
    def __init__(self):
        self.data = {}

    def get_password(self, service, user):
        return self.data.get((service, user))

    def set_password(self, service, user, password):
        self.data[(service, user)] = password

    def delete_password(self, service, user):
        self.data.pop((service, user), None)


memory_keyring = _Memory()


class DemoSmtp:
    def ehlo(self):
        return 250, b""

    def starttls(self, context=None):
        return 220, b""

    def login(self, user, password):
        if password == "faux":
            raise smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")

    def send_message(self, msg):
        time.sleep(0.6)
        if "bounce" in msg["To"]:
            raise smtplib.SMTPRecipientsRefused({msg["To"]: (550, b"5.1.1 The email account does not exist")})

    def quit(self):
        pass


class DemoImap:
    def login(self, user, password):
        if password == "faux":
            raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")

    def logout(self):
        pass

    def noop(self):
        return "OK", [b""]

    def list(self):
        return "OK", [b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"', b'(\\HasNoChildren \\All) "/" "[Gmail]/All Mail"']

    def create(self, name):
        return "OK", [b""]

    def select(self, name, readonly=False):
        return "OK", [b"1"]

    def search(self, charset, *criteria):
        return "OK", [b"1" if criteria[0] == "HEADER" else b""]

    def store(self, num, op, value):
        return "OK", [b""]

    def fetch(self, num, what):
        return "OK", []
