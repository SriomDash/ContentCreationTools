"""
One-command entry point.

    python run.py

Starts the FastAPI app (which seeds sources.csv, starts the 3h scheduler, and
kicks an initial background fetch). Open http://127.0.0.1:8000 in your browser.

Env overrides:
    IDEASLAMP_HOST   (default 127.0.0.1)
    IDEASLAMP_PORT   (default 8000)
"""
import os

import uvicorn

if __name__ == "__main__":
    host = os.environ.get("IDEASLAMP_HOST", "127.0.0.1")
    port = int(os.environ.get("IDEASLAMP_PORT", "8000"))
    print(f"\n  IdeasLamp -> http://{host}:{port}\n")
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
