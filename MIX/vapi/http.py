"""Client HTTP per api.vapi.ai — preferenza IPv6 (IPv4 verso Cloudflare spesso timeout)."""
from __future__ import annotations

import httpx

# GET assistant / health probe
VAPI_TIMEOUT = httpx.Timeout(connect=15.0, read=75.0, write=15.0, pool=15.0)
# POST /call può impiegare fino a ~90–120s lato Vapi/Twilio
VAPI_DIAL_TIMEOUT = httpx.Timeout(connect=15.0, read=120.0, write=15.0, pool=15.0)
# Limite duro per ogni chiamata outbound (8 minuti)
VAPI_MAX_DURATION_SECONDS = 480


def vapi_async_transport() -> httpx.AsyncHTTPTransport:
    try:
        return httpx.AsyncHTTPTransport(local_address="::")
    except OSError:
        return httpx.AsyncHTTPTransport()


def vapi_sync_transport() -> httpx.HTTPTransport:
    try:
        return httpx.HTTPTransport(local_address="::")
    except OSError:
        return httpx.HTTPTransport()
