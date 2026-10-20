"""Windows launcher: bundled server, visible controls, persistent per-user database."""
import os
import sys
from pathlib import Path

if not os.environ.get('OS_DATA_DIR'):
    os.environ['OS_DATA_DIR'] = str(Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'UniversalOS' / 'data')

import ctypes
import datetime
import json
import shutil
import socket
import sqlite3
import threading
import urllib.request
import webbrowser
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
import server
import updater

def backup(destination):
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / ('Universal-OS-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
    source = sqlite3.connect(server.DB)
    output = sqlite3.connect(target)
    try:
        source.backup(output)
    finally:
        output.close()
        source.close()
    return target

def smoke_test(report):
    # Exercise the packaged web assets, SQLite and HTTP server without opening a UI.
    import tkinter as tk
    root = tk.Tk()
    root.iconbitmap(str(server.ROOT / 'public' / 'icon.ico'))
    root.withdraw()
    root.destroy()
    server.initialize()
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url = 'http://127.0.0.1:' + str(httpd.server_port)
    try:
        for route in ['/', '/app.js', '/style.css']:
            with opener.open(url + route, timeout=5) as response:
                assert response.status == 200 and len(response.read()) > 100
        with opener.open(url + '/api/session', timeout=5) as response:
            session = json.load(response)
        assert session['setup'] is True and session['user'] is None
        with server.connect() as c:
            assert c.execute('SELECT next_number FROM settings').fetchone()[0] == 40952
        target = backup(server.DATA / 'backups')
        with sqlite3.connect(target) as c:
            assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        c.close()
        Path(report).write_text(json.dumps({'ok': True, 'checks': ['tkinter', 'http', 'embedded-assets', 'sqlite', 'initial-number', 'backup']}, indent=2), encoding='utf-8')
    finally:
        httpd.shutdown()
        httpd.server_close()

def client_mode():
    import tkinter as tk
    from tkinter import ttk, messagebox
    config = server.DATA.parent / 'client.json'
    saved = ''
    try:
        saved = json.loads(config.read_text(encoding='utf-8'))['url']
    except (OSError, ValueError, KeyError):
        pass
    root = tk.Tk()
    root.iconbitmap(str(server.ROOT / 'public' / 'icon.ico'))
    root.title('Universal OS — Acesso pela rede')
    root.geometry('650x465')
    root.configure(bg='#f3f5f0')
    frame = tk.Frame(root, bg='#f3f5f0', padx=28, pady=24)
    frame.pack(fill='both', expand=True)
    def label(text, size=11, bold=False):
        tk.Label(frame, text=text, bg='#f3f5f0', fg='#244b42', font=('Segoe UI',size,'bold' if bold else 'normal'), justify='left', anchor='w', wraplength=590).pack(fill='x', pady=8)
    label('UNIVERSAL OS · ACESSO PELA REDE', 17, True)
    label('Cole abaixo o endereço exibido no programa do computador principal.\nO computador principal precisa estar ligado e com o programa aberto.')
    label('Endereço do computador principal',10,True)
    entry = ttk.Entry(frame, font=('Segoe UI',12))
    entry.insert(0,saved)
    entry.pack(fill='x', pady=8)
    def open_remote():
        value = entry.get().strip()
        if '://' not in value:
            value = 'http://' + value
        parsed = urlsplit(value)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.hostname in ('localhost','127.0.0.1','0.0.0.0'):
            messagebox.showerror('Confira o endereço','Use o endereço de rede do computador principal, por exemplo http://192.168.1.10:8765/. Não use localhost nos outros PCs.')
            return
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps({'url':value}), encoding='utf-8')
        webbrowser.open(value)
    ttk.Button(frame,text='SALVAR ENDEREÇO E ABRIR',command=open_remote).pack(fill='x',pady=12,ipady=7)
    label('Exemplo: http://192.168.1.10:8765/ — use o IP real do computador principal.',9)
    updater.attach(root, frame, server.DATA, False)
    if saved:
        root.after(800,open_remote)
    root.mainloop()

def run():
    import tkinter as tk
    from tkinter import messagebox, filedialog
    from tkinter import ttk

    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, 'Local\\UniversalOSDesktop8765')
    if ctypes.windll.kernel32.GetLastError() == 183:
        webbrowser.open('http://localhost:8765/')
        return
    root = tk.Tk()
    root.iconbitmap(str(server.ROOT / 'public' / 'icon.ico'))
    root.withdraw()
    try:
        # Import only when the destination has never existed. Never overwrite an existing database.
        exe_folder = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
        if not server.DB.exists():
            for candidate in [exe_folder / 'data' / 'universal.sqlite3', exe_folder / 'Universal-OS' / 'data' / 'universal.sqlite3']:
                if candidate.exists() and candidate.resolve() != server.DB:
                    if messagebox.askyesno('Registros anteriores', 'Encontrei um banco da versão anterior ao lado do programa. Deseja importar esses registros?'):
                        server.DATA.mkdir(parents=True, exist_ok=True)
                        source = sqlite3.connect(candidate)
                        dest = sqlite3.connect(server.DB)
                        try:
                            source.backup(dest)
                        finally:
                            source.close()
                            dest.close()
                    break
        server.initialize()
        with server.connect() as c:
            first = c.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
        try:
            httpd = ThreadingHTTPServer(('0.0.0.0', 8765), server.Handler)
        except OSError:
            # An older copy may already be serving. Confirm its API before opening.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            try:
                with opener.open('http://127.0.0.1:8765/api/session', timeout=3) as response:
                    value = json.load(response)
                if 'defaults' not in value or 'setup' not in value:
                    raise ValueError()
                messagebox.showinfo('Universal OS já aberto', 'O servidor já está funcionando. Vou abrir o navegador. Mantenha a janela da versão anterior aberta enquanto usar o sistema.')
                webbrowser.open('http://localhost:8765/')
                root.destroy()
                return
            except Exception:
                raise RuntimeError('A porta 8765 está ocupada por outro programa. Feche a outra cópia ou reinicie o computador e abra o Universal OS novamente.')
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        root.title('Universal OS — Programa em funcionamento')
        root.geometry('680x800' if first else '680x600')
        root.minsize(640, 600)
        root.configure(bg='#f3f5f0')
        frame = tk.Frame(root, bg='#f3f5f0', padx=30, pady=24)
        frame.pack(fill='both', expand=True)
        def label(text, size=11, bold=False, color='#244b42'):
            w = tk.Label(frame, text=text, bg='#f3f5f0', fg=color, font=('Segoe UI',size,'bold' if bold else 'normal'), anchor='w', justify='left', wraplength=570)
            w.pack(fill='x', pady=5)
            return w
        label('DESPACHANTE UNIVERSAL', 19, True)
        label('●  Programa funcionando', 12, True, '#197149')
        label('O sistema abrirá no navegador. Mantenha esta janela aberta.\nEndereço neste computador: http://localhost:8765/')
        addresses = []
        try:
            for info in socket.getaddrinfo(socket.gethostname(), 8765, socket.AF_INET, socket.SOCK_STREAM):
                address = info[4][0]
                if not address.startswith('127.') and address not in addresses:
                    addresses.append(address)
        except OSError:
            pass
        label('NOS OUTROS COMPUTADORES DA MESMA REDE', 10, True)
        if addresses:
            network_url = 'http://' + addresses[0] + ':8765/'
            entry = ttk.Entry(frame, font=('Consolas',12))
            entry.insert(0, network_url)
            entry.configure(state='readonly')
            entry.pack(fill='x', pady=5)
            def copy_address():
                root.clipboard_clear()
                root.clipboard_append(network_url)
                root.update()
            ttk.Button(frame, text='Copiar endereço para os outros PCs', command=copy_address).pack(fill='x', pady=3)
            if len(addresses) > 1:
                label('Outros endereços deste computador: ' + ', '.join('http://' + a + ':8765/' for a in addresses[1:]), 9)
        else:
            label('Conecte este computador ao Wi-Fi ou cabo da rede e abra o programa novamente.', 10)
        label('Se o Windows perguntar, permita acesso somente em redes privadas.\nO computador principal deve ficar ligado, sem suspender.', 9)
        if first:
            label('PRIMEIRO ACESSO', 11, True)
            label('1. Clique em Copiar código.\n2. Na tela do navegador, cole no campo Código de configuração.\n3. Escolha seu nome, usuário e senha para entrar.', 10)
            code = ttk.Entry(frame, font=('Consolas',11))
            code.insert(0,server.SETUP_TOKEN)
            code.configure(state='readonly')
            code.pack(fill='x', pady=6)
            def copy_code():
                root.clipboard_clear()
                root.clipboard_append(server.SETUP_TOKEN)
                root.update()
                webbrowser.open('http://localhost:8765/')
            ttk.Button(frame, text='Copiar código e abrir cadastro', command=copy_code).pack(fill='x', pady=4)
        ttk.Button(frame, text='ABRIR O PROGRAMA', command=lambda: webbrowser.open('http://localhost:8765/')).pack(fill='x', pady=9, ipady=8)
        def save_backup():
            destination = filedialog.askdirectory(title='Escolha onde guardar a cópia de segurança')
            if destination:
                try:
                    target = backup(Path(destination))
                    messagebox.showinfo('Backup concluído', 'Cópia salva em:\n' + str(target))
                except Exception as e:
                    messagebox.showerror('Falha no backup', str(e))
        ttk.Button(frame, text='Fazer cópia de segurança', command=save_backup).pack(fill='x', pady=4)
        label('Registros salvos em:\n' + str(server.DATA), 9, color='#617168')
        def close():
            if messagebox.askyesno('Encerrar o programa?', 'Encerrar o Universal OS? Os outros computadores ficarão sem acesso até você abrir novamente. Os registros salvos serão mantidos.'):
                httpd.shutdown()
                httpd.server_close()
                root.destroy()
        updater.attach(root, frame, server.DATA, True, lambda: (httpd.shutdown(), httpd.server_close()))
        root.protocol('WM_DELETE_WINDOW', close)
        root.deiconify()
        root.after(900, lambda: webbrowser.open('http://localhost:8765/'))
        root.mainloop()
    except Exception as e:
        messagebox.showerror('Universal OS — não foi possível iniciar', str(e))
        root.destroy()
    finally:
        if mutex:
            ctypes.windll.kernel32.CloseHandle(mutex)

if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        smoke_test(sys.argv[2])
    elif '--cliente' in sys.argv:
        client_mode()
    else:
        run()
