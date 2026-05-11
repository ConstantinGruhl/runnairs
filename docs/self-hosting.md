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

OIDC / single sign-on:

1. Set `PUBLIC_BASE_URL` to the frontend's externally reachable origin (for example `https://platform.example.com`) so the control plane can build the canonical callback URI.
2. Register an application at your IdP using `${PUBLIC_BASE_URL}/api/auth/oidc/callback` as the redirect URI.
3. Sign in as an admin and go to `Admin -> Authentication`.
4. Paste the discovery URL, click `Test discovery`, and confirm the issuer is reachable before saving.
5. Fill in `client_id`, `client_secret`, `scopes`, the email and (optionally) role claim, the claim-to-role map, and the default role; enable the provider.
6. Flip the instance to `hybrid` mode first, sign in with SSO at least once, and only then switch to `oidc` mode if you want to make SSO authoritative.
7. The bootstrap admin always keeps a built-in password as a break-glass account. If SSO breaks, the bootstrap admin can still sign in through the standard login form even when `auth_mode == "oidc"`.

Removing the provider while the instance is in `hybrid` or `oidc` mode automatically demotes the mode back to `built_in` so logins never fall off a cliff. Disabling JIT provisioning forces every OIDC user to be pre-created locally before they can sign in.

Explicitly deferred from this phase:

- multiple OIDC providers per instance and per-tenant providers
- SAML support
- OIDC RP-initiated logout and end-session redirect handling
- provider-driven user provisioning (SCIM)

Operational concerns to handle outside this demo repo:

- external TLS and ingress
- secrets injection and rotation
- postgres backups and point-in-time recovery
- centralized logs and metrics
- image build / runtime strategy for deployed automations
