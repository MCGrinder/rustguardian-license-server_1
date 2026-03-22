# RustGuardian License System v2

This is a full starter licensing backend for RustGuardian.

## What it includes
- License validation endpoint
- Per-server binding
- Expiry handling
- Revoke support
- Reset bindings support
- Admin endpoints
- SQLite by default
- Render-ready deployment

## Files
- `main.py` - FastAPI app
- `database.py` - DB connection
- `models.py` - license + activation tables
- `requirements.txt`
- `render.yaml`

## Local run
```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Render deploy
1. Upload all files to GitHub
2. Create a Render Web Service
3. Use the repo
4. Deploy
5. In Render, copy the `ADMIN_SECRET` environment variable value or set your own

## Default database
By default it uses:
```text
sqlite:///./licenses.db
```

For production, switch `DATABASE_URL` to Postgres later.

## Main public endpoint
### POST `/validate-license`
Request:
```json
{
  "license_key": "RG-ABCD-EFGH-JKLM-NPQR",
  "server_id": "20834398",
  "app_version": "1.0.1"
}
```

## Admin endpoints
These require header:
```text
x-admin-secret: YOUR_ADMIN_SECRET
```

### Create license
`POST /admin/licenses`

Example body:
```json
{
  "customer_name": "Example User",
  "customer_email": "user@example.com",
  "plan": "single_server",
  "server_limit": 1,
  "duration_days": 30,
  "notes": "Discord purchase"
}
```

### List licenses
`GET /admin/licenses`

### Get one license
`GET /admin/licenses/{license_key}`

### Extend a license
`POST /admin/licenses/{license_key}/extend`

Body:
```json
{
  "duration_days": 30
}
```

### Revoke a license
`POST /admin/licenses/{license_key}/revoke`

Body:
```json
{
  "reason": "Chargeback"
}
```

### Reset server bindings
`POST /admin/licenses/{license_key}/reset-bindings`

Body:
```json
{
  "reason": "Customer changed server"
}
```

## Connect from RustGuardian
Example:
```python
import requests

def check_license(base_url: str, license_key: str, server_id: str, version: str):
    response = requests.post(
        f"{base_url}/validate-license",
        json={
            "license_key": license_key,
            "server_id": server_id,
            "app_version": version,
        },
        timeout=10,
    )
    data = response.json()
    return data.get("valid", False), data
```

## Important note
SQLite is fine to start, but on Render's filesystem it is not suitable for long-term production use. Move to a managed database before scaling.
