"""
MySQL backup (free: mysqldump use karta hai). Usage:  python scripts/backup_db.py [output_dir]
Config wahi .env se aati hai jo app use karti hai (local ya Aiven, SSL ke saath).
Cron example (roz raat 2 baje):  0 2 * * * cd /path/GreenBEE && python scripts/backup_db.py backups
Restore:  mysql -h HOST -u USER -p DBNAME < backups/<file>.sql
"""
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config  # noqa: E402


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "backups"
    os.makedirs(out_dir, exist_ok=True)
    cfg = Config.DB_CONFIG
    path = os.path.join(out_dir, f"{cfg['database']}_{datetime.now():%Y%m%d_%H%M%S}.sql")

    cmd = ["mysqldump", f"--host={cfg['host']}", f"--port={cfg['port']}", f"--user={cfg['user']}",
           "--single-transaction", "--routines", "--triggers", "--set-gtid-purged=OFF", "--no-tablespaces",
           cfg["database"]]
    if cfg.get("ssl_ca"):
        cmd.insert(1, f"--ssl-ca={cfg['ssl_ca']}")
    env = dict(os.environ, MYSQL_PWD=cfg.get("password") or "")  # password command line par nahi aata

    with open(path, "w", encoding="utf-8") as f:
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, env=env, text=True)
    if result.returncode != 0:
        os.remove(path)
        print("❌ Backup failed:", result.stderr.strip())
        sys.exit(1)
    print(f"✅ Backup saved: {path} ({os.path.getsize(path) // 1024} KB)")


if __name__ == "__main__":
    main()
