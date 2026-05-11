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

Use the production overlay for the supported self-hosted baseline:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Minimum production expectations:

- set `APP_ENV=production`
- set a strong `JWT_SECRET`
- provide a real `PLATFORM_SECRETS_KEY`
- terminate TLS at your ingress or reverse proxy
- keep `INTERNAL_API_URL` pointed at the internal control-plane service for the frontend proxy layer

Operational concerns to handle outside this demo repo:

- external TLS and ingress
- secrets injection and rotation
- postgres backups and point-in-time recovery
- centralized logs and metrics
- image build / runtime strategy for deployed automations
