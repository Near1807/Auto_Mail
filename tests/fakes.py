"""Faux serveurs SMTP / IMAP : aucun test n'ouvre de connexion réseau."""

from __future__ import annotations

import re
import smtplib
from email import message_from_bytes


class FakeSmtp:
    """Se comporte comme ``smtplib.SMTP`` pour ce que ``SmtpSession`` utilise."""

    def __init__(self, server: "FakeSmtpServer"):
        self.server = server
        self.closed = False
        server.connections += 1

    def ehlo(self):
        return 250, b"ok"

    def starttls(self, context=None):
        return 220, b"ok"

    def login(self, user, password):
        if password != self.server.password:
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")
        self.server.logins += 1

    def send_message(self, msg):
        if self.closed:
            raise smtplib.SMTPServerDisconnected("closed")
        to = msg["To"]
        if self.server.disconnect_before.pop(to, False):
            self.closed = True
            raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
        if to in self.server.refuse:
            raise smtplib.SMTPRecipientsRefused({to: (550, b"5.1.1 No such user")})
        if self.server.on_send:
            self.server.on_send(msg)
        self.server.sent.append(msg)

    def quit(self):
        self.closed = True


class FakeSmtpServer:
    def __init__(self, password: str = "secret"):
        self.password = password
        self.sent = []
        self.refuse: set[str] = set()
        self.disconnect_before: dict[str, bool] = {}
        self.connections = 0
        self.logins = 0
        self.on_send = None

    def factory(self):
        return FakeSmtp(self)

    @property
    def recipients(self) -> list[str]:
        return [m["To"] for m in self.sent]


class FakeImap:
    """Sous-ensemble d'``imaplib.IMAP4_SSL`` façon Gmail."""

    def __init__(self, server: "FakeImapServer"):
        self.server = server
        self.selected = None

    def login(self, user, password):
        if password != self.server.password:
            import imaplib

            raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")
        return "OK", [b"ok"]

    def logout(self):
        return "BYE", [b""]

    def noop(self):
        self.server.noops += 1
        return "OK", [b""]

    def list(self):
        lines = []
        for name in self.server.folders:
            flags = self.server.special.get(name, "\\HasNoChildren")
            lines.append(f'({flags}) "/" "{name}"'.encode())
        return "OK", lines

    def create(self, name):
        self.server.folders.append(name.strip('"'))
        self.server.created.append(name.strip('"'))
        return "OK", [b""]

    def select(self, name, readonly=False):
        self.selected = name.strip('"')
        return ("OK", [b"1"]) if self.selected in self.server.folders else ("NO", [b""])

    def search(self, charset, *criteria):
        msgs = self.server.messages
        if criteria[0] == "HEADER":
            mid = criteria[2].strip('"')
            if self.server.index_delay.get(mid, 0) > 0:
                self.server.index_delay[mid] -= 1
                return "OK", [b""]
            nums = [str(i + 1).encode() for i, m in enumerate(msgs) if m["mid"] == mid]
        elif criteria[0] == "X-GM-RAW":
            label = criteria[1].strip('"').split(":", 1)[1]
            nums = [str(i + 1).encode() for i, m in enumerate(msgs)
                    if any(re.sub(r"[\s/]+", "-", l) == label for l in m["labels"])]
        elif criteria[0] == "X-GM-THRID":
            nums = [str(i + 1).encode() for i, m in enumerate(msgs) if m["thread"] == criteria[1]]
        else:
            nums = []
        return "OK", [b" ".join(nums)]

    def store(self, num, op, value):
        labels = re.findall(r'"((?:[^"\\]|\\.)*)"', value)
        self.server.messages[int(num) - 1]["labels"].update(labels)
        return "OK", [b""]

    def fetch(self, num, what):
        m = self.server.messages[int(num) - 1]
        headers = f"From: {m['from']}\r\nTo: {m['to']}\r\nDate: {m['date']}\r\n\r\n".encode()
        return "OK", [(f"{num} (X-GM-THRID {m['thread']} BODY[HEADER] {{{len(headers)}}}".encode(), headers), b")"]


class FakeImapServer:
    def __init__(self, password: str = "secret"):
        self.password = password
        self.folders = ["INBOX", "[Gmail]/Messages envoy&AOk-s", "[Gmail]/Tous les messages"]
        self.special = {"[Gmail]/Messages envoy&AOk-s": "\\HasNoChildren \\Sent",
                        "[Gmail]/Tous les messages": "\\HasNoChildren \\All"}
        self.messages: list[dict] = []
        self.created: list[str] = []
        self.index_delay: dict[str, int] = {}
        self.noops = 0

    def factory(self):
        return FakeImap(self)

    def add(self, mid, frm, to, thread, date="Mon, 19 Oct 2026 10:00:00 +0200", labels=()):
        self.messages.append({"mid": mid, "from": frm, "to": to, "thread": thread, "date": date,
                              "labels": set(labels)})

    def record_sent(self, msg):
        """À brancher sur ``FakeSmtpServer.on_send`` : le mail arrive dans « Envoyés »."""
        self.add(msg["Message-ID"], msg["From"], msg["To"], thread=str(1000 + len(self.messages)))


def parse(msg):
    return message_from_bytes(msg.as_bytes())
