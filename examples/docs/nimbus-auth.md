# Nimbus API — Authentication

- Nimbus uses **bearer tokens**. Send `Authorization: Bearer <token>`.
- Tokens are scoped to a single project and expire after **24 hours**.
- Refresh a token with `POST /auth/refresh`; the refresh token is valid for
  **30 days**.
- There is no API-key-in-URL auth — keys in the query string are rejected with
  `401 auth_in_url_forbidden`.
