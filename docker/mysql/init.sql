-- WebPanel MySQL initialisation
-- Runs once on first start
-- NOTE: % is required instead of a specific subnet because MySQL Docker image
-- resolves '%' to all hosts, and Docker Compose services have dynamic IPs.
-- Docker network isolation (separate data_net) is used as the primary access
-- control layer instead.

CREATE DATABASE IF NOT EXISTS webpanel;
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP, LOCK TABLES, EXECUTE
  ON webpanel.* TO 'webpanel'@'%';
FLUSH PRIVILEGES;

-- PowerDNS schema
CREATE DATABASE IF NOT EXISTS pdns;
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP
  ON pdns.* TO 'webpanel'@'%';
FLUSH PRIVILEGES;

-- Revoke dangerous privileges that the application should never need
REVOKE CREATE USER, FILE, PROCESS, RELOAD, REPLICATION CLIENT, REPLICATION SLAVE, SHOW DATABASES, SHUTDOWN, SUPER
  ON *.* FROM 'webpanel'@'%';
FLUSH PRIVILEGES;
