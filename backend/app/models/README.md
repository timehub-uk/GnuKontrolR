# backend/app/models/

SQLAlchemy ORM models. All tables are created via `Base.metadata.create_all` in `database.py`.

| Model | Table | Description |
|---|---|---|
| `User` | `users` | Panel users with role-based access |
| `Domain` | `domains` | Customer domains (owned by a user) |
| `ContainerPort` | `container_ports` | Persistent unique port allocations per domain/service |
| `RequestLog` | `request_logs` | Per-user API request activity log |

## User roles

`superadmin > admin > reseller > user`

Role guards are defined in `auth.py`: `require_superadmin`, `require_admin`, `require_reseller`.

## Adding a new model

1. Create `my_model.py` inheriting from `Base`
2. Import it in `database.py`'s `init_db()` to register it with `metadata`
