"""Native menu for the single Universal OS window."""
import datetime
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import threading
import urllib.request
from urllib.parse import urlsplit
import updater
from backup_scheduler import BackupScheduler
from native_dialogs import network_dialog, backup_dialog

class NativeTools:
    def __init__(self, data, is_server, url):
        self.data = Path(data)
        self.is_server = is_server
        self.url = url
        self.window = None
        self.stopped = threading.Event()
        self.lock = threading.Lock()
        self.scheduler = BackupScheduler(self.data, self.stopped) if is_server else None

    def menu(self):
        from webview.menu import Menu, MenuAction
        items = [MenuAction('Buscar atualização', lambda: self.check(True)),
                 MenuAction('Informações da rede', self.network)]
        if self.is_server:
            items.append(MenuAction('Fazer cópia de segurança', self.backup))
            items.append(MenuAction('Backup automático — Google Drive', self.configure_backup))
        items.append(MenuAction('Sobre o Universal OS', lambda: self.info('Universal OS', 'Versão ' + updater.VERSION + '\n\nUse Minha senha para trocar a senha. O administrador redefine acessos em Configurações.')))
        return [Menu('Programa', items)]

    def info(self, title, message):
        return self.window.create_confirmation_dialog(title, message)

    def bind(self, window):
        self.window = window
        window.events.closed += self.stopped.set
        threading.Thread(target=self.periodic, daemon=True).start()
        if self.scheduler:
            self.scheduler.start()

    def periodic(self):
        if self.stopped.wait(4):
            return
        while not self.stopped.is_set():
            self.check(False)
            if self.stopped.wait(6 * 60 * 60):
                return

    def network(self):
        if self.is_server:
            addresses = []
            try:
                for item in socket.getaddrinfo(socket.gethostname(), 8765, socket.AF_INET, socket.SOCK_STREAM):
                    address = item[4][0]
                    if not address.startswith('127.') and address not in addresses:
                        addresses.append(address)
            except OSError:
                pass
            network_dialog(['http://' + address + ':8765/' for address in addresses], True)
        else:
            network_dialog([self.url], False)

    def configure_backup(self):
        try:
            self.administrator()
            backup_dialog(self.scheduler, self.administrator)
        except Exception as error:
            self.info('Backup automático', str(error))

    def administrator(self):
        pairs = []
        for cookie in self.window.get_cookies():
            for morsel in cookie.values():
                pairs.append(morsel.key + '=' + morsel.value)
        parsed = urlsplit(self.url)
        request = urllib.request.Request(parsed.scheme + '://' + parsed.netloc + '/api/session', headers={'Cookie': '; '.join(pairs)})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=5) as response:
            user = json.load(response).get('user')
        if not user or not user.get('admin'):
            raise ValueError('Entre no programa com um usuário administrador para fazer o backup completo.')

    def backup(self):
        try:
            self.administrator()
            import webview
            selected = self.window.create_file_dialog(webview.FileDialog.FOLDER)
            if not selected:
                return
            folder = Path(selected[0])
            target = folder / ('Universal-OS-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
            source = sqlite3.connect(self.data / 'universal.sqlite3', timeout=30)
            output = sqlite3.connect(target)
            try:
                source.backup(output)
                if output.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Falha ao conferir o backup.')
            finally:
                source.close()
                output.close()
            self.info('Backup concluído', 'Cópia salva em:\n' + str(target))
        except Exception as error:
            self.info('Cópia de segurança', str(error))

    def check(self, manual=False):
        if not self.lock.acquire(blocking=False):
            return
        accepted = False
        try:
            manifest = updater.fetch_manifest()
            if updater.version_tuple(manifest['version']) <= updater.version_tuple(updater.VERSION):
                if manual:
                    self.info('Universal OS', 'Você já está usando a versão mais recente: ' + updater.VERSION)
                return
            text = 'Versão ' + manifest['version'] + ' disponível.\n\n' + manifest.get('notes', '') + '\n\nSalve as OS antes de continuar. Deseja baixar e abrir o instalador agora?'
            if not self.window.create_confirmation_dialog('Atualização do Universal OS', text):
                return
            accepted = True
            installer = updater.download_installer(manifest, self.data.parent / 'updates')
            if self.is_server:
                updater.backup_before_update(self.data)
            args = [str(installer), '/ROLE=' + ('server' if self.is_server else 'client')]
            if getattr(sys, 'frozen', False):
                args.append('/DIR=' + str(Path(sys.executable).parent))
            subprocess.Popen(args)
            self.window.confirm_close = False
            self.window.destroy()
        except Exception as error:
            if manual or accepted:
                self.info('Não foi possível atualizar', str(error)[:500] + '\n\nO uso do programa continua disponível.')
        finally:
            self.lock.release()
