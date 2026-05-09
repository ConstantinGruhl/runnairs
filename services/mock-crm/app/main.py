from fastapi import FastAPI, HTTPException

app = FastAPI(title="Mock CRM")


_CUSTOMERS = {
    "acme": {
        "id": "acme",
        "name": "Acme Corp",
        "owner": "alice@example.com",
        "tier": "enterprise",
        "open_opportunities": 3,
        "last_contacted": "2026-04-22",
    },
    "globex": {
        "id": "globex",
        "name": "Globex",
        "owner": "bob@example.com",
        "tier": "mid-market",
        "open_opportunities": 1,
        "last_contacted": "2026-05-01",
    },
    "initech": {
        "id": "initech",
        "name": "Initech",
        "owner": "carol@example.com",
        "tier": "smb",
        "open_opportunities": 0,
        "last_contacted": "2026-03-14",
    },
}


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "mock-crm"}


@app.get("/customers/{customer_id}")
def get_customer(customer_id: str) -> dict:
    customer = _CUSTOMERS.get(customer_id.lower())
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return customer


@app.get("/customers")
def list_customers() -> list[dict]:
    return list(_CUSTOMERS.values())
