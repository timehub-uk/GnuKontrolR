-- WebPanel MySQL initialisation
-- Runs once on first start

CREATE DATABASE IF NOT EXISTS webpanel;
GRANT ALL PRIVILEGES ON webpanel.* TO 'webpanel'@'%';
FLUSH PRIVILEGES;

-- PowerDNS schema
CREATE DATABASE IF NOT EXISTS pdns;
GRANT ALL PRIVILEGES ON pdns.* TO 'webpanel'@'%';
FLUSH PRIVILEGES;
