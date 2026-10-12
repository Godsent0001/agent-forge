"""SSRF guard for outbound HTTP tools.

This rejects non-public destinations before a request and is applied to every
redirect hop. DNS rebinding between validation and connection remains a known
limitation unless the HTTP transport pins the validated IP address.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeURL(ValueError):
    """Raised when a URL is not safe for outbound requests."""


def assert_public_url(url: str, *, app_port: int | None = None) -> None:
    """Allow only public HTTP(S) destinations.

    Reject localhost names, private/reserved IPs, nonstandard schemes, invalid
    ports, and the app's own listening port when supplied.
    """
    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise UnsafeURL("Invalid URL") from exc

    if scheme not in {"http", "https"} or not host:
        raise UnsafeURL("Only absolute HTTP(S) URLs are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeURL("URLs containing credentials are not allowed")
    if port is not None and not 1 <= port <= 65535:
        raise UnsafeURL("Invalid destination port")
    if app_port is not None and port == app_port:
        raise UnsafeURL("Requests to the application's own port are not allowed")

    normalized = host.rstrip(".").lower()
    if normalized == "localhost" or normalized.endswith(".localhost") or normalized.endswith(".local"):
        raise UnsafeURL("Local hostnames are not allowed")

    try:
        addresses = {ipaddress.ip_address(normalized)}
    except ValueError:
        try:
            records = socket.getaddrinfo(normalized, port or (443 if scheme == "https" else 80), type=socket.SOCK_STREAM)
        except OSError as exc:
            raise UnsafeURL("Destination hostname could not be resolved") from exc
        addresses = {ipaddress.ip_address(record[4][0].split("%", 1)[0]) for record in records}

    if not addresses:
        raise UnsafeURL("Destination hostname has no addresses")
    for address in addresses:
        if (
            address.is_loopback
            or address.is_private
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise UnsafeURL("Requests to private or special-use network addresses are not allowed")
