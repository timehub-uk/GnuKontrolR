# Privacy Policy

**Last Updated:** June 9, 2026

---

## 1. Data Controller

GnuKontrolR (the "Platform") acts as a data controller for the personal data collected from its users. For questions about this policy, contact the superadmin.

## 2. What Data We Collect

### 2.1 Account Data
- Username, email address, full name
- Billing and contact information (address, phone, company, VAT)
- Account preferences and settings

### 2.2 Usage Data
- IP addresses (stored as hashed values)
- API request logs (method, path, status, timestamp)
- Domain and DNS configurations
- Container and service usage data

### 2.3 Communications
- Support inquiries and correspondence
- Notification preferences

## 3. Lawful Basis for Processing

We process personal data under the following lawful bases:

| Processing Activity | Lawful Basis |
|---------------------|-------------|
| Account management | Contract (performance of services) |
| Billing | Legal obligation |
| Security monitoring | Legitimate interest |
| Marketing communications | Consent |
| Support services | Contract (performance of services) |
| Compliance reporting | Legal obligation |

## 4. How We Use Your Data

- To provide, maintain, and improve platform services
- To process billing and payments
- To monitor and ensure platform security
- To communicate with you about your account
- To comply with legal obligations
- To detect and prevent fraud or abuse

## 5. Data Sharing & Third Parties

We do not sell personal data. Data may be shared with:

| Third Party | Purpose | Data Shared |
|-------------|---------|-------------|
| Docker (infrastructure) | Container orchestration | None (infrastructure layer) |
| MySQL/PostgreSQL | Database storage | Account data |
| Redis | Caching | Session identifiers |
| Let's Encrypt | SSL certificate issuance | Domain names |
| PowerDNS | DNS resolution | Domain records |

All third-party processors are bound by Data Processing Agreements.

## 6. Data Retention

| Data Category | Retention Period |
|---------------|-----------------|
| Account data | Duration of account + 30 days |
| Request logs | 1000 entries per user (auto-pruned) |
| Financial records | 7 years (legal obligation) |
| Backup data | 30 days |
| Session tokens | Until expiry or logout |

## 7. Your Rights (GDPR)

You have the right to:
- **Access** your personal data (Article 15)
- **Rectification** of inaccurate data (Article 16)
- **Erasure** ("right to be forgotten") (Article 17)
- **Restrict** processing (Article 18)
- **Data portability** (Article 20)
- **Object** to processing (Article 21)

To exercise these rights, use the privacy settings in your account or submit a DSAR via the compliance section.

## 8. Cookies & Tracking

We use essential cookies for authentication and security:
- Session tokens (JWT stored in memory)
- CSRF protection tokens
- Preference cookies

We do not use tracking cookies or third-party analytics.

## 9. Data Security

We implement appropriate technical and organizational measures including:
- Encryption in transit (TLS 1.2+)
- Access controls and authentication
- Regular security monitoring
- Incident response procedures
- Regular backups

## 10. Breach Notification

In the event of a data breach that poses a risk to your rights, we will notify you within 72 hours and report to the relevant supervisory authority as required by GDPR Article 33-34.

## 11. Contact

For privacy-related inquiries, contact the superadmin through the platform dashboard.
