# Backup and restore drill

## Where backups live

The `graxia-backup.timer` on the VPS runs `/usr/local/sbin/graxia-backup` (source: `deploy/vps/graxia-backup`) once a day, around 20:20 UTC. Each run writes a directory named after its UTC timestamp:

```
/var/backups/graxia/<stamp>/      e.g. /var/backups/graxia/20261101T202244Z/
  graxia-production.dump.age      Graxia production DB (pg_dump -Fc --no-owner --no-acl of `graxia`)
  automation.dump.age, windmill.dump.age, sanso-production.dump.age, ...
  config.tar.gz.age
  SHA256SUMS, manifest.json
```

Every file is encrypted with `age` to the public key in `/etc/graxia/backup.age.pub`. The private key is not on the VPS, so backups cannot be decrypted there. Retention is the newest 7 directories plus one per ISO week for the last 4 weeks.

An offsite copy of the same directories is kept on the user's PC at `C:\graxia\offsite-backups\<stamp>\`.

## Monthly restore drill

Do this on the 1st of each month. It proves the latest dump decrypts and restores, and measures how long a restore takes. Production is only read (row counts in a read-only transaction); the restore goes into a throwaway container with no network that is removed afterwards.

1. On the machine that holds the age private key, pick the newest backup and check its checksum, then decrypt the production dump:

   ```bash
   cd /c/graxia/offsite-backups/<stamp>
   sha256sum -c SHA256SUMS
   age -d -i <key> -o graxia-production.dump graxia-production.dump.age
   ```

2. Copy the decrypted dump and the drill script to the VPS:

   ```bash
   ssh opportunity-vps 'install -d -m 700 /root/drill'
   scp graxia-production.dump opportunity-vps:/root/drill/
   scp "<repo>/deploy/vps/restore-drill.sh" opportunity-vps:/root/drill/
   ```

3. Run the drill on the VPS:

   ```bash
   ssh opportunity-vps 'bash /root/drill/restore-drill.sh /root/drill/graxia-production.dump'
   ```

   The script starts a container from the same image as `graxia_prod_postgres` (currently `pgvector/pgvector:pg17`), restores the dump, counts rows in every public table on both sides, and prints `tables_restored`, `rto_seconds` (container start to restore finished) and a diff of the counts. Differences are expected only in tables that received writes after the backup was taken; a missing table or a large gap means the backup is bad. The script exits non-zero if the dump is still encrypted, the container does not become ready within 120 s (`DRILL_WAIT_S`), or `pg_restore` fails.

4. Delete the decrypted dump on both machines:

   ```bash
   ssh opportunity-vps 'rm -rf /root/drill'
   rm graxia-production.dump
   ```

5. Write down the date, backup stamp, `rto_seconds` and whether counts matched, so the next drill has something to compare against.

The VPS root disk is around 87% full. The production dump is small (under 1 MB encrypted), but check `df -h /` before the drill if it has grown a lot.
