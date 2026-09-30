"""Local-only HTTP transport for the maintained inference runners (Python 3.10)."""
import http.client
import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request

URL = "http://127.0.0.1:9001"


def validate_base_url(url):
    """Accept a literal loopback origin, without DNS or credential-bearing URL fields."""
    error = "inference URL must be an HTTP(S) origin with a literal loopback IP and valid port; no credentials, path, query or fragment"
    try:
        parsed = urllib.parse.urlsplit(url)
        address = ipaddress.ip_address(parsed.hostname or "")
        port = parsed.port
        loopback = address.is_loopback if address.version == 4 else address == ipaddress.IPv6Address("::1")
        valid = (parsed.scheme in ("http", "https") and loopback
                 and parsed.username is None and parsed.password is None
                 and parsed.path in ("", "/") and "?" not in url and "#" not in url
                 and "%" not in parsed.netloc and not parsed.netloc.endswith(":")
                 and (port is None or 1 <= port <= 65535)
                 and not any(ord(char) <= 32 or ord(char) == 127 for char in url))
    except ValueError:
        raise ValueError(error) from None
    if not valid:
        raise ValueError(error)
    return url.rstrip("/")


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        # Reject before urllib parses Location: even a malformed header can echo credentials.
        raise urllib.error.HTTPError(req.full_url, code, "redirects disabled", headers, fp)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirects())


class InferenceResponseError(RuntimeError):
    """An error category safe to log without the server's response or request data."""


def request_json(path, timeout=10, url=URL, data=None):
    """Send directly to loopback; never follow redirects or expose HTTP error payloads."""
    base = validate_base_url(url)
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("inference endpoint must be an absolute path, not a URL")
    request = urllib.request.Request(base + path, data=data,
                                     headers={"Content-Type": "application/json"})
    try:
        with _DIRECT.open(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # The server controls the reason, headers and body; any of them can echo the key.
        error.close()
        raise urllib.error.HTTPError(request.full_url, error.code, "inference request failed", {}, None) from None
    except (urllib.error.URLError, http.client.HTTPException, UnicodeError, json.JSONDecodeError) as error:
        raise InferenceResponseError(f"{type(error).__name__}: inference response failed") from None
