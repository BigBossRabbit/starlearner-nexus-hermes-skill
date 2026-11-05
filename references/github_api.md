# GitHub REST API Reference

Concise reference for the GitHub API endpoints used by StarLearner-Nexus.

## Endpoint

- **List starred repositories**: `GET /user/starred`
  - Requires authentication (returns the authenticated user's starred repos).
  - Response: a JSON array of repository objects (full repo metadata).

## Pagination

- The starred-repos endpoint returns up to **100 items per page** by default.
- Use `per_page=100` to maximize items per request:
  ```
  curl -H "Authorization: token $GITHUB_TOKEN" \
       -H "Accept: application/vnd.github+json" \
       "https://api.github.com/user/starred?per_page=100"
  ```
- Paginate through results using the **`Link` header** in the response:
  - `rel="next"` — URL for the next page of results.
  - `rel="last"` — URL for the final page (use to know how many pages remain).
  - Follow `rel="next"` until it is absent to walk all pages.

## Rate Limits

- Unauthenticated requests: **60 requests/hour** (per IP).
- Authenticated requests: **5,000 requests/hour** (per account/token).
- Check current status via the rate-limit endpoint:
  ```
  curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/rate_limit
  ```
- The `X-RateLimit-Remaining` response header shows remaining quota for the current window.

## Authentication Header

All authenticated requests send the token in the `Authorization` header:

```
Authorization: token <GITHUB_TOKEN>
```

Note: the `token` scheme (bearer-style) is the standard form for GitHub PATs. Pass the token via the `$GITHUB_TOKEN` environment variable — never hardcode it.
