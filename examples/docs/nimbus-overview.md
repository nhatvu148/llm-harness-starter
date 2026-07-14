# Nimbus API — Overview

Nimbus is a *fictional* object-storage API used as the demo dataset for this
scaffold. None of this is real — it exists so the retrieval layer has specific
facts to answer from.

- Base URL: `https://api.nimbus.example/v2`
- Objects are grouped into **buckets**; each bucket belongs to one **project**.
- Every response includes an `x-nimbus-request-id` header for support.
- The maximum object size is **5 GiB** per upload. Larger files must use
  multipart upload via `POST /objects/multipart`.
