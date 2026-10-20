"""Daily consistent SQLite snapshots in a user-selected synchronized folder."""
import datetime as dt
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import uuid


class BackupScheduler:
    def __init__(self, data, stopped):
        self.data = Path(data)
        self.config_file = self.data.parent / 'backup-settings.json'
        self.lock = threading.RLock()
        self.stopped = stopped
        self.retry_after = None
        self.config = {'enabled': False, 'folder': '', 'time': '17:30',
                       'instance': uuid.uuid4().hex, 'last_day': '',
                       'last_success': '', 'last_file': '', 'error': ''}
        try:
            saved = json.loads(self.config_file.read_text(encoding='utf-8'))
            if not isinstance(saved, dict):
                raise ValueError('Configuração inválida.')
            self.config.update({k: v for k, v in saved.items() if k in self.config})
            if not re.fullmatch(r'[a-f0-9]{32}', self.config['instance']):
                raise ValueError('Identificação do backup inválida.')
            if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', self.config['time']):
                raise ValueError('Horário inválido.')
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            self.config.update(enabled=False, instance=uuid.uuid4().hex, time='17:30', error='Não foi possível ler a configuração. Escolha novamente a pasta do backup.')

    def status(self):
        with self.lock:
            return dict(self.config)

    def _persist(self):
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.config_file.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, self.config_file)

    def configure(self, enabled, folder, scheduled='17:30'):
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', scheduled):
            raise ValueError('Use um horário como 17:30.')
        if enabled:
            selected = Path(folder).resolve(strict=True)
            if not selected.is_dir():
                raise ValueError('Escolha uma pasta do Google Drive sincronizada neste PC.')
            folder = str(selected)
        with self.lock:
            previous = dict(self.config)
            if folder != self.config['folder'] or scheduled != self.config['time']:
                self.config['last_day'] = ''
            self.config.update(enabled=bool(enabled), folder=folder, time=scheduled, error='')
            try:
                self._persist()
            except Exception:
                self.config = previous
                raise
            self.retry_after = None

    def tick(self, now=None):
        now = now or dt.datetime.now()
        with self.lock:
            if not self.config['enabled'] or now.strftime('%H:%M') < self.config['time']:
                return False
            # A clock moving backwards must not create duplicate daily snapshots.
            if self.config['last_day'] >= now.date().isoformat():
                return False
            if self.retry_after and now < self.retry_after:
                return False
            try:
                self._snapshot(now, scheduled=True)
                self.retry_after = None
                return True
            except Exception as error:
                self.config['error'] = 'Backup pendente: ' + str(error)[:300]
                self.retry_after = now + dt.timedelta(minutes=5)
                try:
                    self._persist()
                except OSError:
                    pass
                return False

    def run_now(self):
        with self.lock:
            return self._snapshot(dt.datetime.now(), scheduled=False)

    def _snapshot(self, now, scheduled):
        if not self.config['folder']:
            raise ValueError('Escolha primeiro a pasta sincronizada do Google Drive.')
        base = Path(self.config['folder']).resolve(strict=True)
        if not base.is_dir():
            raise ValueError('A pasta de backup não está disponível. Confira o Google Drive.')
        destination = base / ('UniversalOS-backups-' + self.config['instance'])
        destination.mkdir(exist_ok=True)
        if destination.is_symlink() or destination.resolve().parent != base:
            raise ValueError('Pasta de backup inválida.')
        name = 'UniversalOS-auto-' + now.strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3'
        target = destination / name
        temporary = target.with_suffix('.sqlite3.part')
        source = output = None
        try:
            # mode=ro refuses to create an empty source database if it is missing.
            source = sqlite3.connect((self.data / 'universal.sqlite3').resolve().as_uri() + '?mode=ro', uri=True, timeout=30)
            output = sqlite3.connect(temporary)
            source.backup(output, pages=256, sleep=.05)
            if output.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Falha ao conferir o banco copiado.')
            output.close()
            output = None
            os.replace(temporary, target)
        finally:
            if output:
                output.close()
            if source:
                source.close()
            temporary.unlink(missing_ok=True)
        self.config.update(last_success=now.isoformat(timespec='seconds'), last_file=str(target), error='')
        if scheduled:
            self.config['last_day'] = now.date().isoformat()
        self._persist()
        # Only our exact filenames in this installation's dedicated folder rotate.
        copies = sorted(p for p in destination.iterdir()
                        if re.fullmatch(r'UniversalOS-auto-\d{8}-\d{6}-\d{6}\.sqlite3', p.name)
                        and p.is_file() and not p.is_symlink())
        for old in copies[:-30]:
            old.unlink()
        return target

    def start(self):
        def worker():
            while not self.stopped.wait(15):
                self.tick()
        threading.Thread(target=worker, daemon=True, name='UniversalOS-backup').start()
