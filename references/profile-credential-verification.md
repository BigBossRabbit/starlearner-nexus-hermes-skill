# Credential Verification for Hermes Profiles

When verifying that each Hermes profile uses its own dedicated API key, check these locations in order:

## 1. Profile-Specific Configuration (Recommended)
Each profile should have isolated credentials in:
```
~/.hermes/profiles/<profile-name>/.env
~/.hermes/profiles/<profile-name>/config.yaml
```

Check individual profile configs:
```bash
# Check orchestrator profile
hermes profile show orchestrator
hermes profile show alan
hermes profile show mira
hermes profile show turing
hermes profile show nova
```

## 2. Global Environment File
Fallback location:
```
~/.hermes/.env
```

## 3. Authentication Storage
Credential storage:
```
~/.hermes/auth.json
```

## 4. Project-Local Configuration
For project-specific overrides:
```
.project/.env
```

## Verification Commands

To verify each profile uses its own key:
```bash
# Check OpenRouter API keys for each profile
hermes profile show orchestrator | grep api_key
hermes profile show alan | grep api_key
hermes profile show mira | grep api_key
hermes profile show turing | grep api_key
hermes profile show nova | grep api_key
```

## Expected Output Format
Each profile should show a different environment variable reference:
- orchestrator: `api_key: ${VICTOR_API_KEY}`
- alan: `api_key: ${OKIN_API_KEY}`
- mira: `api_key: ${GITHUB_API_KEY}`
- turing: `api_key: ${TNNB_API_KEY}`
- nova: `api_key: ${NOVA_API_KEY}`

## Troubleshooting

If profiles show the same key or missing keys:
1. Ensure each profile has its own `.env` file with unique variable names
2. Check that `credential_pool_strategies: openrouter: none` is set in each profile's config.yaml
3. Verify no global `profile:` key in `~/.hermes/config.yaml` is overriding individual profiles
4. Run `hermes doctor` to check for configuration issues