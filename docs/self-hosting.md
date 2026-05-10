# Self-hosting

The supported base stack is:

- `postgres`
- `redis`
- `control-plane`
- `tool-gateway`
- `worker`
- `scheduler`
- `frontend`

Demo-only extras in this repository are:

- `mailhog`
- `mock-crm`
- `sample_data`

Use the production overlay when you want the frontend to talk to the internal control-plane service instead of `localhost`:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Operational concerns to handle outside this demo repo:

- external TLS and ingress
- secrets injection and rotation
- postgres backups and point-in-time recovery
- centralized logs and metrics
- image build / runtime strategy for deployed automations
