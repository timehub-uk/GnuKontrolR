# Getting Started

## Logging In

1. Open your browser to `https://your-panel-domain:8443`
2. Enter the admin username and password you created during installation
3. You'll land on the **Dashboard** with system overview

## Dashboard Overview

The dashboard shows:

- **System Status** — CPU, memory, disk usage
- **Service Health** — status of all Docker services (green = healthy)
- **Recent Activity** — latest system events and CVE alerts
- **Quick Actions** — common tasks

## Your First Domain

### 1. Add a Domain

1. Navigate to **Domains** → **Add Domain**
2. Enter the domain name (e.g., `example.com`)
3. Select the owner (admin or a reseller)
4. Add any notes/tags
5. Click **Save**

### 2. Configure DNS

1. Navigate to **DNS**
2. Select your new domain from the zone list
3. Add DNS records:
   - **A record**: `@` → your server IP
   - **A record**: `www` → your server IP
   - **MX record**: `@` → `mail.your-domain.com`
   - **TXT record**: for DKIM (auto-generated)

### 3. Point Nameservers

At your domain registrar, point the nameservers to your server (or delegate DNS to GnuKontrolR).

## The WebPanel Terminal

The Terminal gives you shell access to the admin container:

- Click **Terminal** in the sidebar
- Run `panel` for the interactive CLI
- Run `panel /list` to see all available commands
- Run standard Linux commands (bash, ls, grep, etc.)

## Creating a Customer Account

1. Go to **Users** → **Add User**
2. Fill in username, email, password
3. Select role: `user` (regular), `reseller`, or `admin`
4. **Save**

## Customer Site (Container)

When you create a domain for a user, a site container is automatically:

- Provisioned with nginx + PHP
- Assigned a unique internal port
- Configured with the domain's DNS records
- Set up with SSL via Let's Encrypt

## First Time Checklist

- [ ] Add your first domain
- [ ] Configure DNS records
- [ ] Verify SSL certificate is issued
- [ ] Test email delivery (SMTP/IMAP)
- [ ] Set up monitoring alerts in Grafana
- [ ] Configure Fail2ban rules in Security tab
- [ ] Create a reseller/user account
