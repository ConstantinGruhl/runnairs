from fastapi import FastAPI

app = FastAPI(title="Agent Platform Tool Gateway")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "tool-gateway"}
