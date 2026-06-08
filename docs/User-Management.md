# User Management

## Roles

| Role | Permissions |
|------|-------------|
| **superadmin** | Full access to all features, settings, users, billing |
| **admin** | Can manage users, domains, services (except system settings) |
| **reseller** | Can create and manage their own customers and domains |
| **user** | Can only manage their own domains and settings |

## Managing Users

### Via Web UI

1. Go to **Users** in the sidebar
2. Click **Add User** to create a new account
3. Click a user to edit their details, role, or status
4. Use the actions menu to delete or suspend a user

### Via CLI

```bash
panel user list
panel user create john john@example.com --password s3cret --role user
panel user reset-pass john --password newpass
panel user delete john
```

### From Host (`setup.sh`)

```bash
sudo bash setup.sh cmd_add_user
# Follow the prompts for username, email, password, role

sudo bash setup.sh cmd_reset_pass
# Follow the prompts to reset any user's password
```

## Account Security

- Passwords are hashed with bcrypt before storage
- JWT tokens expire after configurable duration (default: 24 hours)
- Login attempts are rate-limited
- Failed login events are logged and visible in the Security page

## Support PIN

Each user can have a support PIN for identity verification. Users set this in their profile settings. The PIN is stored as a bcrypt hash.
