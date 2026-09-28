from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("SYSTEMAI_API_HOST", "127.0.0.1")
    port = int(os.environ.get("SYSTEMAI_API_PORT", "8765"))
    uvicorn.run("systemai.api.v1_server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
