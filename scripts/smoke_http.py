"""Start a real Uvicorn process, verify HTTP responses, then shut it down."""

import os, subprocess, sys, tempfile, time, socket
from pathlib import Path
import httpx

with tempfile.TemporaryDirectory() as tmp:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "DATABASE_URL": "sqlite:///" + str(Path(tmp) / "http.db")}
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", trust_env=False
        ) as client:
            for attempt in range(50):
                try:
                    r = client.get("/health")
                    r.raise_for_status()
                    break
                except httpx.ConnectError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Server did not start")
            assert client.get("/openapi.json").status_code == 200
            for v, f in [("v1", "ct200_manual.pdf"), ("v2", "ct200_manual_v2.pdf")]:
                r = client.post(
                    "/versions/" + v,
                    files={
                        "file": (f, Path("data", f).read_bytes(), "application/pdf")
                    },
                )
                r.raise_for_status()
            assert len(client.get("/versions/v2/sections").json()) == 8
            print("PASS: real HTTP health, OpenAPI, both PDF imports, section browsing")
    finally:
        process.terminate()
        process.wait(timeout=10)
