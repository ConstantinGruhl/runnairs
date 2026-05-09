from fastapi import FastAPI

app = FastAPI(title="Agent Platform Control Plane")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "control-plane"}
