# Credential & Profile Isolation Audit

Each Hermes profile should use its own dedicated, isolated API key so that no
single credential is shared across profiles or leaked into another profile's
session.

## Where Profile Credentials Live

Profile-specific configuration and secrets are stored per profile:

```
~/.hermes/profiles/<PROFILE_NAME>/.env          # profile API keys (secrets only)
~/.hermes/profiles/<PROFILE_NAME>/config.yaml   # profile settings (no secrets)
```

A global fallback exists at `~/.hermes/.env` and OAuth tokens live in
`~/.hermes/auth.json` — but the recommended pattern is one dedicated key per
profile.

## Verification

Confirm each profile references its own unique environment variable rather
than sharing one:

```bash
hermes profile show <PROFILE_NAME>
# Expected: api_key: ${PROFILE_KEY_1}  (a unique var per profile)
```

## Troubleshooting

1. If profiles resolve to the same key, give each its own `.env` with a unique
   variable name and point the profile's `config.yaml` at it.
2. Ensure no global `profile:` block in `~/.hermes/config.yaml` overrides
   individual profiles.
3. Run `hermes doctor` to surface configuration or credential issues.