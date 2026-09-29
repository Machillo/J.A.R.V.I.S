"""Outbound network guard for Labs: loopback only, fail closed.

Installed by ``labs.runtime.activate`` before any backend module is imported.
Every TCP/UDP connection and every name lookup goes through the socket module,
so blocking there covers requests, httpx, smtplib, psycopg2's Python-side
lookups and the store/Gmail/Discord clients alike. Only loopback addresses and
local socket paths are allowed: the Labs database runs on this machine.

psycopg2 connects from C (libpq), below this guard; that path is covered by
``labs.guard.check_database_url`` (local hosts only, no redirecting options),
no PG* variable reaching the process, and ``labs.db`` checking after connecting
that the server's address is loopback. Proxies are disabled (environment and the
operating system's settings). Known gap: the Windows asyncio proactor connects
below socket.connect; the backend makes no asyncio network calls today.
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


def _disable_proxies() -> None:
    """No proxy, ever: a system proxy on loopback (Windows registry, macOS settings) would carry
    traffic off the machine through an allowed local port."""
    import os
    import urllib.request

    def no_proxies(*_args, **_kwargs):
        return {}

    for name in ("getproxies", "getproxies_environment", "getproxies_registry", "getproxies_macosx_sysconf"):
        if hasattr(urllib.request, name):
            setattr(urllib.request, name, no_proxies)
    for name in list(os.environ):
        if name.upper().endswith("_PROXY") and name.upper() != "NO_PROXY":
            del os.environ[name]
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"


def install() -> None:
    """Idempotently restrict this process to loopback networking, without proxies."""
    if _ORIGINAL:
        return
    _disable_proxies()
    _ORIGINAL["getaddrinfo"] = socket.getaddrinfo
    _ORIGINAL["connect"] = socket.socket.connect
    _ORIGINAL["connect_ex"] = socket.socket.connect_ex
    _ORIGINAL["sendto"] = socket.socket.sendto
    _ORIGINAL["sendmsg"] = getattr(socket.socket, "sendmsg", None)
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

    def sendmsg(self, buffers, ancdata=(), flags=0, address=None):
        if address is not None:
            _check_address(address)
            return _ORIGINAL["sendmsg"](self, buffers, ancdata, flags, address)
        return _ORIGINAL["sendmsg"](self, buffers, ancdata, flags)

    def create_connection(address, *args, **kwargs):
        _check_address(address)
        return _ORIGINAL["create_connection"](address, *args, **kwargs)

    socket.getaddrinfo = getaddrinfo
    socket.gethostbyname = gethostbyname
    socket.gethostbyname_ex = gethostbyname_ex
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.socket.sendto = sendto
    if _ORIGINAL["sendmsg"] is not None:
        socket.socket.sendmsg = sendmsg
    socket.create_connection = create_connection


def installed() -> bool:
    return bool(_ORIGINAL)
