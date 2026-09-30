from __future__ import annotations

import uvicorn

from systemai.config import Settings


def main() -> None:
    settings = Settings()
    if settings.api_host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("SystemAI API must bind to loopback")
    uvicorn.run("systemai.api.local_server:app", host=settings.api_host, port=settings.api_port, reload=False)


if __name__ == "__main__":
    main()
