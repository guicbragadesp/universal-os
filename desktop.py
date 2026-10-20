"""Single-window Windows application with central SQLite server or LAN client."""
import os
import sys
from pathlib import Path
if not os.environ.get('OS_DATA_DIR'):
    os.environ['OS_DATA_DIR'] = str(Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'UniversalOS' / 'data')
import ctypes
import datetime
import json
import sqlite3
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
import server
import updater
from native_tools import NativeTools

def message(title, text):
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    try:
        messagebox.showerror(title, text, parent=root)
    finally:
        root.destroy()

def valid_url(url, remote=False):
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Endereço inválido para o Universal OS.')
    if remote and parsed.hostname in ('localhost', '127.0.0.1', '0.0.0.0', '::1'):
        raise ValueError('Use o IP do computador principal, por exemplo http://192.168.1.10:8765/.')
    if parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise ValueError('Informe somente o endereço e a porta do computador principal.')
    return url.rstrip('/') + '/'

def run_web_window(url, is_server=False, first=False):
    import webview
    url = valid_url(url)
    tools = NativeTools(server.DATA, is_server, url)
    webview.settings['ALLOW_DOWNLOADS'] = True
    webview.settings['ALLOW_FILE_URLS'] = False
    window = webview.create_window('Universal OS', url, width=1280, height=850,
        min_size=(900, 620), text_select=True, zoomable=True, confirm_close=is_server)
    def loaded():
        if first and window.get_current_url().rstrip('/') == url.rstrip('/'):
            # Only this local server's first setup receives its one-time setup token.
            window.evaluate_js("""(function(){var attempts=0;var timer=setInterval(function(){var field=document.getElementById('token');if(field){field.value=""" + json.dumps(server.SETUP_TOKEN) + """;field.closest('.field').style.display='none';var text=document.querySelector('.login-main .muted');if(text)text.textContent='Crie seu nome, usuário e senha para começar.';clearInterval(timer);}if(++attempts>100)clearInterval(timer);},100);})();""")
    window.events.loaded += loaded
    tools.bind(window)
    webview.start(gui='edgechromium', private_mode=True, menu=tools.menu(),
        localization={'global.quitConfirmation':'Encerrar o Universal OS? Os outros computadores ficarão sem acesso até você abrir novamente. Salve as OS antes de sair.',
                      'global.ok':'OK', 'global.cancel':'Cancelar', 'global.quit':'Encerrar'},
        icon=str(server.ROOT / 'public' / 'icon.ico'))

def smoke_web_window(report):
    import webview
    server.initialize()
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    window = webview.create_window('Universal OS', 'http://127.0.0.1:' + str(httpd.server_port), hidden=True)
    result = {}
    def verify():
        try:
            if not window.events.loaded.wait(35):
                raise RuntimeError('A janela integrada não carregou.')
            value = window.evaluate_js("JSON.stringify({login:!!document.querySelector('#login-form'),print:typeof window.print})")
            result.update(json.loads(value))
            result['renderer'] = webview.guilib.renderer
            assert result['login'] and result['print'] == 'function' and result['renderer'] == 'edgechromium'
            result['ok'] = True
        except Exception as error:
            result.update(ok=False, error=str(error))
        finally:
            Path(report).write_text(json.dumps(result, indent=2), encoding='utf-8')
            window.destroy()
    webview.start(verify, gui='edgechromium', private_mode=True, storage_path=str(server.DATA / 'webview-test'), icon=str(server.ROOT / 'public' / 'icon.ico'))
    httpd.shutdown()
    httpd.server_close()


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

def client_mode(force_config=False):
    config = server.DATA.parent / 'client.json'
    saved = ''
    try:
        saved = valid_url(json.loads(config.read_text(encoding='utf-8'))['url'], remote=True)
    except (OSError, ValueError, KeyError):
        pass
    if saved and not force_config:
        return run_web_window(saved)
    import tkinter as tk
    from tkinter import ttk, messagebox
    root = tk.Tk()
    root.iconbitmap(str(server.ROOT / 'public' / 'icon.ico'))
    root.title('Universal OS — Configurar rede')
    root.geometry('650x340')
    frame = ttk.Frame(root, padding=28)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Endereço do computador principal', font=('Segoe UI',16,'bold')).pack(pady=12)
    ttk.Label(frame, text='O principal deve estar ligado e com o Universal OS aberto.').pack(pady=8)
    entry = ttk.Entry(frame, font=('Segoe UI',12))
    entry.insert(0, saved)
    entry.pack(fill='x', pady=12)
    selected = []
    def save():
        try:
            value = entry.get().strip()
            if '://' not in value:
                value = 'http://' + value
            value = valid_url(value, remote=True)
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(json.dumps({'url':value}), encoding='utf-8')
            selected.append(value)
            root.destroy()
        except (ValueError, OSError) as error:
            messagebox.showerror('Confira o endereço', str(error), parent=root)
    ttk.Button(frame, text='Salvar e abrir', command=save).pack(fill='x', pady=12)
    ttk.Label(frame, text='Exemplo: http://192.168.1.10:8765/').pack(pady=8)
    root.mainloop()
    if selected:
        run_web_window(selected[0])

def import_legacy():
    if server.DB.exists():
        return
    exe_folder = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    for candidate in [exe_folder/'data'/'universal.sqlite3', exe_folder/'Universal-OS'/'data'/'universal.sqlite3']:
        if candidate.exists() and candidate.resolve() != server.DB:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            try:
                accept = messagebox.askyesno('Registros anteriores', 'Encontrei um banco da versão anterior ao lado do programa. Deseja importar esses registros?', parent=root)
            finally:
                root.destroy()
            if accept:
                server.DATA.mkdir(parents=True, exist_ok=True)
                source = sqlite3.connect(candidate)
                dest = sqlite3.connect(server.DB)
                try:
                    source.backup(dest)
                finally:
                    source.close()
                    dest.close()
            break

def run():
    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    mutex = kernel.CreateMutexW(None, False, 'Local\\UniversalOSDesktop8765')
    if not mutex:
        raise OSError('Não foi possível iniciar o controle de instância do programa.')
    httpd = None
    try:
        if kernel.GetLastError() == 183:
            user = ctypes.windll.user32
            user.FindWindowW.restype = ctypes.c_void_p
            user.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user.SetForegroundWindow.argtypes = [ctypes.c_void_p]
            existing = user.FindWindowW(None, 'Universal OS')
            if existing:
                user.ShowWindow(existing, 9)
                user.SetForegroundWindow(existing)
            return
        import_legacy()
        server.initialize()
        with server.connect() as c:
            first = c.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
        try:
            httpd = ThreadingHTTPServer(('0.0.0.0', 8765), server.Handler)
        except OSError:
            raise RuntimeError('A porta 8765 está em uso. Feche a versão anterior do Universal OS ou reinicie o computador e abra novamente.')
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        run_web_window('http://localhost:8765/', is_server=True, first=first)
    finally:
        if httpd:
            httpd.shutdown()
            httpd.server_close()
        kernel.CloseHandle(mutex)

if __name__ == '__main__':
    try:
        if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
            smoke_test(sys.argv[2])
        elif len(sys.argv) == 3 and sys.argv[1] == '--web-self-test':
            smoke_web_window(sys.argv[2])
        elif len(sys.argv) == 3 and sys.argv[1] == '--web-window':
            run_web_window(sys.argv[2])
        elif '--configurar-rede' in sys.argv:
            client_mode(True)
        elif '--cliente' in sys.argv:
            client_mode()
        else:
            run()
    except Exception as error:
        message('Universal OS — não foi possível abrir', str(error) + '\n\nSe o componente WebView2 estiver ausente, reinstale a atualização com acesso à internet.')
