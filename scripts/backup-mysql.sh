#!/bin/bash
# Run on the VM as root. Copy this backup off the VM before treating it as durable.
set -euo pipefail
umask 077
install -d -m 700 /var/backups/student
backup="/var/backups/student/studentdb-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
k3s kubectl -n student exec deployment/mysql -- sh -ec \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction --no-tablespaces studentdb' | gzip > "$backup"
gzip -t "$backup"
printf 'Backup created: %s\nCopy off the VM and test restoration.\n' "$backup"
