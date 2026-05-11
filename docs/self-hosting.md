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
- plan to finish the first-run `/setup` flow before exposing the platform to regular users

First-run built-in IAM flow:

1. Launch the stack and open the frontend.
2. The platform routes fresh instances into `/setup` and keeps normal app routes locked.
3. Select `Built-in IAM`, create the bootstrap admin, and store the bootstrap recovery code offline.
4. Resolve any blocked runtime checks such as `JWT_SECRET` or `PLATFORM_SECRETS_KEY`.
5. Complete setup, then sign in normally through the built-in login flow.
6. Use `Admin -> Users` to create workspace accounts, change roles, disable access, or generate one-time reset and recovery codes.

Recovery path:

- The bootstrap admin receives a one-time offline recovery code during initial setup. Store it outside the platform.
- The login screen supports both password-reset codes and the bootstrap recovery code.
- Admins can generate one-time reset or recovery codes for workspace users from `Admin -> Users` without database edits.
- External IAM and OIDC are not part of this phase yet; built-in IAM is the supported production path on this branch.

Operational concerns to handle outside this demo repo:

- external TLS and ingress
- secrets injection and rotation
- postgres backups and point-in-time recovery
- centralized logs and metrics
- image build / runtime strategy for deployed automations
