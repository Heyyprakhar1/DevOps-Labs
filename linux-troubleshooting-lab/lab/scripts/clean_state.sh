#!/bin/bash
# Reset Linux Lab sandbox container to clean production baseline

echo "[linuxlab] Cleaning lab environment..."

# 1. Kill any runaway CPU/Memory/Rogue processes
sudo pkill -9 -f "stress" 2>/dev/null
sudo pkill -9 -f "worker_loop" 2>/dev/null
sudo pkill -9 -f "cryptonight" 2>/dev/null
sudo pkill -9 -f "mem_eater" 2>/dev/null
sudo pkill -9 -f "rogue_listener" 2>/dev/null
sudo pkill -9 -f "nc -l" 2>/dev/null
sudo pkill -9 -f "netcat" 2>/dev/null
sudo pkill -9 -f "hog_process" 2>/dev/null

# 2. Clean temporary files, inode hogs, bloated logs
sudo mount -o remount,rw /var/spool/app_cache 2>/dev/null || true
sudo rm -rf /tmp/stress_* /tmp/sess_* /tmp/bloat_* /tmp/inode_bomb* 2>/dev/null
sudo rm -rf /var/spool/app_cache/* 2>/dev/null
sudo rm -f /var/log/app/disk_hog.log /var/log/app/transaction.log /tmp/large_log.dump 2>/dev/null

# Recreate directories with proper permissions
sudo mkdir -p /var/spool/app_cache /var/log/app /etc/app /run/services /opt/services
sudo chmod 777 /var/spool/app_cache /tmp
sudo chmod 755 /var/log/app /etc/app /run/services /opt/services

# 3. Restore default configuration files
cat <<'EOF' | sudo tee /etc/app/web_app.conf > /dev/null
{
  "port": 8080,
  "workers": 4,
  "debug": false
}
EOF

cat <<'EOF' | sudo tee /etc/app/payment.conf > /dev/null
{
  "port": 8000,
  "db_host": "127.0.0.1",
  "db_port": 5432,
  "timeout": 3
}
EOF

sudo chmod 644 /etc/app/web_app.conf /etc/app/payment.conf
sudo chown -R devops:devops /etc/app /opt/services /var/log/app /run/services

# 4. Clean simulated hosts entries if any were injected
grep -v '# linuxlab-injected' /etc/hosts | sudo tee /etc/hosts > /dev/null

# 5. Reset log files with a baseline message
echo "$(date '+%b %d %H:%M:%S') $(hostname) web-app[1]: Service baseline initialized." | sudo tee /var/log/app/web_app.log > /dev/null
echo "$(date '+%b %d %H:%M:%S') $(hostname) payment-api[1]: Service baseline initialized." | sudo tee /var/log/app/payment.log > /dev/null
sudo chown -R devops:devops /var/log/app

# 6. Restart baseline services
/usr/local/bin/systemctl restart web-app 2>/dev/null
/usr/local/bin/systemctl restart payment-api 2>/dev/null

echo "[linuxlab] Environment reset complete and services verified."
