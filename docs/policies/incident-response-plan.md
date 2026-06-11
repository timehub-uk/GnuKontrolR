# Incident Response Plan (IRP)

**Document ID:** IRP-001  
**Version:** 1.0  
**Effective Date:** June 9, 2026  

---

## 1. Purpose

This Incident Response Plan defines the process for identifying, containing, eradicating, and recovering from security incidents affecting the GnuKontrolR platform.

## 2. Incident Classification

| Severity | Definition | Response Time | Examples |
|----------|------------|---------------|----------|
| **Critical** | Active breach, data exposure, service outage | < 1 hour | Unauthorized access, ransomware, data exfiltration |
| **High** | Probable breach, significant vulnerability | < 4 hours | Malware detection, compromised credentials, DoS attack |
| **Medium** | Potential security issue, policy violation | < 24 hours | Suspicious activity, misconfiguration, weak passwords |
| **Low** | Minor issue, best practice gap | < 72 hours | Missing security headers, outdated software |

## 3. Response Team

| Role | Responsibility |
|------|---------------|
| **Incident Commander** | Overall coordination and decision-making |
| **Technical Lead** | Investigation, containment, and remediation |
| **Communications Lead** | Internal and external notifications |
| **Legal/Compliance Lead** | Regulatory reporting and legal requirements |

## 4. Response Phases

### 4.1 Preparation
- Maintain up-to-date contact information for the response team
- Ensure backup systems are operational
- Conduct tabletop exercises quarterly
- Keep incident response tools available

### 4.2 Detection & Analysis
- Monitor security alerts (fail2ban, CVE feed, scanner, Prometheus)
- Validate and classify incidents
- Document initial findings
- Preserve evidence

### 4.3 Containment
- Isolate affected systems (disable accounts, block IPs, stop containers)
- Apply temporary mitigations
- Document containment actions
- Prevent lateral movement

### 4.4 Eradication
- Remove malicious code or unauthorized access
- Patch vulnerabilities
- Reset compromised credentials
- Verify complete removal

### 4.5 Recovery
- Restore from clean backups if needed
- Return systems to normal operation
- Monitor for recurrence
- Communicate restoration to stakeholders

### 4.6 Post-Incident Review
- Conduct root cause analysis within 5 business days
- Document lessons learned
- Update policies and controls
- Report findings to management

## 5. Notification Requirements

### 5.1 Internal Notifications
- Critical/high incidents: Notify all admins immediately via platform notifications and email
- Medium incidents: Notify within 24 hours
- Low incidents: Include in weekly report

### 5.2 External Notifications (GDPR)
- **DPA notification:** Within 72 hours for high-risk breaches (Art. 33)
- **Affected data subjects:** Without undue delay for high-risk breaches (Art. 34)
- Content: Nature of breach, categories of data, contact information, recommended mitigation

### 5.3 Law Enforcement
- Notify relevant authorities as required by applicable law

## 6. Evidence Collection

- Preserve logs, screenshots, and system state
- Maintain chain of custody
- Document timeline of events
- Secure forensic evidence

## 7. Communication Templates

### Breach Notification to DPA
> Subject: Data Breach Notification - [Date]
> 
> We are notifying you of a personal data breach pursuant to GDPR Article 33.
> 
> Nature of breach: [description]
> Categories of data affected: [categories]
> Approximate number of data subjects: [number]
> Point of contact: [name/email]
> Measures taken: [actions]

### Breach Notification to Affected Users
> Subject: Security Incident Notification
> 
> We are writing to inform you of a security incident affecting your account.
> 
> What happened: [brief description]
> What we have done: [actions taken]
> What you should do: [recommended actions]
> Contact: [support information]

## 8. Testing

The Incident Response Plan will be tested:
- Tabletop exercises: Quarterly
- Full simulation: Annually
- Backup restoration: Quarterly
- Post-incident review: After every incident

---

**Approved by:** Management  
**Date:** June 9, 2026
