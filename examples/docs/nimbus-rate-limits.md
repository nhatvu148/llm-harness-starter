# Nimbus API — Rate limits

- Default limit: **600 requests per minute** per project.
- Uploads are limited separately to **60 uploads per minute**.
- Bursts of up to **100 requests** are allowed before the per-minute limit
  applies.
- When throttled, Nimbus returns `429` with a `Retry-After` header (seconds).
- Enterprise projects can request a raise to **6,000 requests per minute**.
