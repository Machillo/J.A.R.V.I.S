"""Outbound network guard for Labs: loopback only, fail closed.

Installed by ``labs.runtime.activate`` before any backend module is imported.
Every TCP/UDP connection and every name lookup goes through the socket module,
so blocking there covers requests, httpx, smtplib, psycopg2's Python-side
lookups and the store/Gmail/Discord clients alike. Only loopback addresses and
local socket paths are allowed: the Labs database runs on this machine.

psycopg2 connects from C (libpq), below this guard; that path is covered by
``labs.guard.check_database_url`` (local host only) and by the Labs DSN being
the only database the backend is given.
"""
from __future__ import annotations

import ipaddress
import socket

_ORIGINAL = {}


class NetworkBlocked(ConnectionError):
    """Labs tried to reach a non-local address."""


def _local(host) -> bool:
    if host is None:
        return False
    if isinstance(host, (bytes, bytearray)):
        host = host.decode("ascii", "ignore")
    host = str(host)
    if host in {"localhost", "localhost.localdomain", ""}:
        return host != ""
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _check_address(address) -> None:
    if isinstance(address, (str, bytes)):  # AF_UNIX path
        return
    host = address[0] if isinstance(address, tuple) and address else None
    if not _local(host):
        raise NetworkBlocked(f"Labs blocks outbound network to {host!r}; only loopback is allowed")


def install() -> None:
    """Idempotently restrict this process to loopback networking."""
    if _ORIGINAL:
        return
    _ORIGINAL["getaddrinfo"] = socket.getaddrinfo
    _ORIGINAL["connect"] = socket.socket.connect
    _ORIGINAL["connect_ex"] = socket.socket.connect_ex
    _ORIGINAL["sendto"] = socket.socket.sendto
    _ORIGINAL["gethostbyname"] = socket.gethostbyname
    _ORIGINAL["gethostbyname_ex"] = socket.gethostbyname_ex
    _ORIGINAL["create_connection"] = socket.create_connection

    def getaddrinfo(host, *args, **kwargs):
        if not _local(host):
            raise NetworkBlocked(f"Labs blocks name resolution of {host!r}; only loopback is allowed")
        return _ORIGINAL["getaddrinfo"](host, *args, **kwargs)

    def gethostbyname(host):
        if not _local(host):
            raise NetworkBlocked(f"Labs blocks name resolution of {host!r}")
        return _ORIGINAL["gethostbyname"](host)

    def gethostbyname_ex(host):
        if not _local(host):
            raise NetworkBlocked(f"Labs blocks name resolution of {host!r}")
        return _ORIGINAL["gethostbyname_ex"](host)

    def connect(self, address):
        _check_address(address)
        return _ORIGINAL["connect"](self, address)

    def connect_ex(self, address):
        _check_address(address)
        return _ORIGINAL["connect_ex"](self, address)

    def sendto(self, data, *args):
        _check_address(args[-1])
        return _ORIGINAL["sendto"](self, data, *args)

    def create_connection(address, *args, **kwargs):
        _check_address(address)
        return _ORIGINAL["create_connection"](address, *args, **kwargs)

    socket.getaddrinfo = getaddrinfo
    socket.gethostbyname = gethostbyname
    socket.gethostbyname_ex = gethostbyname_ex
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.socket.sendto = sendto
    socket.create_connection = create_connection


def installed() -> bool:
    return bool(_ORIGINAL)
