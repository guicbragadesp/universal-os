"""Updates from the public Universal OS feed; no client records leave the PC."""
import hashlib
import json
from pathlib import Path
import queue
import re
import sqlite3
import subprocess
import sys
import threading
import urllib.request
from urllib.parse import urlsplit
import datetime

VERSION = '1.16.0'
FEED_URL = 'https://raw.githubusercontent.com/guicbragadesp/universal-os/main/latest.json'
DOWNLOAD_PREFIX = 'https://github.com/guicbragadesp/universal-os/releases/download/'
MAX_DOWNLOAD = 150 * 1024 * 1024

def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,6}\.\d{1,6}\.\d{1,6}', value):
        raise ValueError('Versão de atualização inválida.')
    return tuple(int(x) for x in value.split('.'))

def validate_manifest(value):
    if not isinstance(value, dict) or value.get('app') != 'universal-os' or value.get('schema') != 1:
        raise ValueError('O servidor retornou um catálogo de atualização inválido.')
    version_tuple(value.get('version'))
    url = value.get('installer_url', '')
    if not isinstance(url, str) or not url.startswith(DOWNLOAD_PREFIX) or urlsplit(url).query or not url.endswith('.exe'):
        raise ValueError('O instalador não pertence ao endereço oficial do Universal OS.')
    if not isinstance(value.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', value['sha256']):
        raise ValueError('A conferência do arquivo não está disponível.')
    if type(value.get('size')) is not int or not 0 < value['size'] <= MAX_DOWNLOAD:
        raise ValueError('Tamanho de atualização inválido.')
    notes = value.get('notes', '')
    if not isinstance(notes, str) or len(notes) > 6000:
        raise ValueError('Descrição da atualização inválida.')
    return value

def fetch_manifest():
    request = urllib.request.Request(FEED_URL, headers={'User-Agent': 'UniversalOS/' + VERSION, 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(request, timeout=15) as response:
        if urlsplit(response.url).scheme != 'https':
            raise ValueError('Conexão de atualização insegura.')
        data = response.read(65537)
    if len(data) > 65536:
        raise ValueError('Catálogo de atualização muito grande.')
    return validate_manifest(json.loads(data.decode('utf-8')))

def download_installer(manifest, folder):
    validate_manifest(manifest)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    name = 'Instalar-Universal-OS-' + manifest['version'] + '.exe'
    target = folder / name
    partial = folder / (name + '.part')
    digest = hashlib.sha256()
    size = 0
    try:
        request = urllib.request.Request(manifest['installer_url'], headers={'User-Agent': 'UniversalOS/' + VERSION})
        with urllib.request.urlopen(request, timeout=30) as response, partial.open('wb') as out:
            if urlsplit(response.url).scheme != 'https':
                raise ValueError('Conexão de download insegura.')
            while True:
                block = response.read(1024 * 128)
                if not block:
                    break
                size += len(block)
                if size > manifest['size']:
                    raise ValueError('O arquivo recebido tem tamanho inesperado.')
                digest.update(block)
                out.write(block)
        if size != manifest['size'] or digest.hexdigest() != manifest['sha256']:
            raise ValueError('O arquivo não passou pela conferência. Nada foi instalado. Tente baixar novamente.')
        partial.replace(target)
        return target
    finally:
        if partial.exists():
            partial.unlink()

def backup_before_update(data):
    db = Path(data) / 'universal.sqlite3'
    if not db.exists():
        return None
    folder = db.parent / 'backups'
    folder.mkdir(exist_ok=True)
    target = folder / ('antes-atualizacao-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
    source = sqlite3.connect(db, timeout=30)
    output = sqlite3.connect(target)
    try:
        source.backup(output)
        if output.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Não foi possível conferir o backup. A atualização foi interrompida.')
    finally:
        source.close()
        output.close()
    return target

def attach(root, frame, data_dir, is_server, stop=None):
    from tkinter import ttk, messagebox
    events = queue.Queue()
    state = {'busy': False}
    status = ttk.Label(frame, text='Versão ' + VERSION + ' · Verificação pela internet')
    status.pack(fill='x', pady=3)
    button = ttk.Button(frame, text='Buscar atualização')
    button.pack(fill='x', pady=3)

    def worker_check(manual):
        try:
            events.put(('checked', fetch_manifest(), manual))
        except Exception as error:
            events.put(('check-error', str(error), manual))

    def check(manual=False):
        if state['busy']:
            return
        state['busy'] = True
        status.configure(text='Verificando novas versões…')
        button.configure(state='disabled')
        threading.Thread(target=worker_check, args=(manual,), daemon=True).start()

    def worker_download(manifest):
        try:
            installer = download_installer(manifest, Path(data_dir).parent / 'updates')
            if is_server:
                backup_before_update(data_dir)
            events.put(('downloaded', str(installer), None))
        except Exception as error:
            events.put(('download-error', str(error), None))

    def poll():
        try:
            while True:
                kind, value, manual = events.get_nowait()
                if kind == 'checked':
                    state['busy'] = False
                    button.configure(state='normal')
                    if version_tuple(value['version']) <= version_tuple(VERSION):
                        status.configure(text='Versão ' + VERSION + ' · Você está atualizado')
                        if manual:
                            messagebox.showinfo('Universal OS', 'Você já está usando a versão mais recente.', parent=root)
                    else:
                        status.configure(text='Nova versão disponível: ' + value['version'])
                        message = 'A versão ' + value['version'] + ' está disponível.\n\n' + value.get('notes', '') + '\n\nSalve as OS abertas antes de continuar. Deseja baixar e abrir o instalador agora?'
                        if messagebox.askyesno('Atualização do Universal OS', message, parent=root):
                            state['busy'] = True
                            button.configure(state='disabled')
                            status.configure(text='Baixando e conferindo o instalador…')
                            threading.Thread(target=worker_download, args=(value,), daemon=True).start()
                elif kind in ('check-error', 'download-error'):
                    state['busy'] = False
                    button.configure(state='normal')
                    status.configure(text='Não foi possível atualizar. O programa continua disponível.')
                    if manual or kind == 'download-error':
                        messagebox.showerror('Atualização indisponível', str(value)[:500], parent=root)
                elif kind == 'downloaded':
                    try:
                        role = '/ROLE=' + ('server' if is_server else 'client')
                        args = [value, role]
                        if getattr(sys, 'frozen', False):
                            args.append('/DIR=' + str(Path(sys.executable).parent))
                        subprocess.Popen(args)
                        if stop:
                            stop()
                        root.destroy()
                        return
                    except Exception as error:
                        state['busy'] = False
                        button.configure(state='normal')
                        messagebox.showerror('Não foi possível abrir o instalador', str(error), parent=root)
        except queue.Empty:
            pass
        root.after(250, poll)

    def periodic():
        check(False)
        root.after(6 * 60 * 60 * 1000, periodic)
    button.configure(command=lambda: check(True))
    root.after(250, poll)
    root.after(3000, periodic)
