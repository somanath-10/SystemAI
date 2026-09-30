from urllib.parse import urlsplit


def browser_origin(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("browser URL must be HTTP(S) without credentials")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("non-loopback browser origins require HTTPS")
    return f"{parsed.scheme}://{parsed.hostname}{f':{parsed.port}' if parsed.port else ''}"
