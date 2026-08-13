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
# Check each Legion profile
hermes profile show thanos
hermes profile show brainiac
hermes profile show riddler
hermes profile show loki
hermes profile show doctor-doom
hermes profile show lex-luthor
hermes profile show kingpin
hermes profile show watcher
hermes profile show joker
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

To verify each profile uses its own dedicated key:
```bash
# Check the API key reference for each Legion profile
hermes profile show thanos | grep api_key
hermes profile show brainiac | grep api_key
hermes profile show riddler | grep api_key
hermes profile show loki | grep api_key
hermes profile show doctor-doom | grep api_key
hermes profile show lex-luthor | grep api_key
hermes profile show kingpin | grep api_key
hermes profile show watcher | grep api_key
hermes profile show joker | grep api_key
```

## Expected Output Format

Each profile should reference a **different** environment variable (its own dedicated API key). No profile should share or inherit another profile's key, and no key value should be hardcoded — only the `${VAR}` reference should appear in config.

## Troubleshooting

If profiles show the same key or missing keys:
1. Ensure each profile has its own `.env` file with unique variable names
2. Check that `credential_pool_strategies: openrouter: none` is set in each profile's config.yaml
3. Verify no global `profile:` key in `~/.hermes/config.yaml` is overriding individual profiles
4. Run `hermes doctor` to check for configuration issues
