"""Short, selectable native dialogs; no persistent second control window."""
import threading
import queue

DIALOG_LOCK = threading.Lock()


def network_dialog(addresses, is_server):
    if not DIALOG_LOCK.acquire(blocking=False):
        return
    import tkinter as tk
    from tkinter import ttk
    root = None
    try:
        root = tk.Tk()
        root.title('Rede do Universal OS')
        root.geometry('680x' + str(340 + max(1, len(addresses)) * 48))
        root.resizable(False, False)
        root.attributes('-topmost', True)
        frame = ttk.Frame(root, padding=24)
        frame.pack(fill='both', expand=True)
        title = 'Endereço para os outros computadores' if is_server else 'Computador principal configurado'
        ttk.Label(frame, text=title, font=('Segoe UI', 13, 'bold')).pack(anchor='w', pady=(0, 16))
        status = tk.StringVar()
        for address in addresses:
            row = ttk.Frame(frame)
            row.pack(fill='x', pady=5)
            value = ttk.Entry(row, font=('Consolas', 12))
            value.insert(0, address)
            value.configure(state='readonly')
            value.pack(side='left', fill='x', expand=True, padx=(0, 10))
            value.bind('<FocusIn>', lambda event: event.widget.selection_range(0, 'end'))
            def copy(text=address, entry=value):
                root.clipboard_clear()
                root.clipboard_append(text)
                root.update()
                entry.focus_set()
                entry.selection_range(0, 'end')
                status.set('Endereço copiado. Cole com Ctrl+V no outro PC ou na mensagem para ele.')
            ttk.Button(row, text='Copiar endereço', command=copy).pack(side='right')
        if not addresses:
            ttk.Label(frame, text='Conecte o computador à rede do escritório.').pack(anchor='w')
        note = ('Mantenha o Universal OS aberto e o principal ligado para atender a rede.\nEste aviso pode ser fechado.' if is_server else
                'Para mudar o endereço, use Configurar rede do Universal OS no menu Iniciar.')
        ttk.Label(frame, text=note, wraplength=620).pack(anchor='w', pady=12)
        ttk.Label(frame, textvariable=status, wraplength=620).pack(anchor='w', pady=5)
        ttk.Button(frame, text='Fechar', command=root.destroy).pack(anchor='e', pady=8)
        root.mainloop()
    finally:
        if root:
            try:
                root.destroy()
            except tk.TclError:
                pass
        DIALOG_LOCK.release()


def backup_dialog(scheduler, authorize):
    if not DIALOG_LOCK.acquire(blocking=False):
        return
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    root = None
    try:
        root = tk.Tk()
        root.title('Backup automático — Google Drive')
        root.geometry('740x640')
        root.resizable(False, False)
        root.attributes('-topmost', True)
        frame = ttk.Frame(root, padding=24)
        frame.pack(fill='both', expand=True)
        cfg = scheduler.status()
        enabled = tk.BooleanVar(value=bool(cfg['enabled']))
        folder = tk.StringVar(value=cfg['folder'])
        scheduled = tk.StringVar(value=cfg['time'])
        state = tk.StringVar()
        ttk.Label(frame, text='Backup diário no Google Drive', font=('Segoe UI', 16, 'bold')).pack(anchor='w', pady=(0, 12))
        ttk.Label(frame, text='Escolha uma pasta sincronizada pelo Google Drive para computador.\nO programa cria o arquivo; o Google Drive faz o envio para a nuvem.', wraplength=680).pack(anchor='w', pady=8)
        ttk.Checkbutton(frame, text='Ativar backup automático diário', variable=enabled).pack(anchor='w', pady=8)
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=8)
        ttk.Label(row, text='Horário do computador:').pack(side='left', padx=(0, 12))
        ttk.Entry(row, textvariable=scheduled, width=8).pack(side='left')
        ttk.Label(frame, text='Pasta do Google Drive:').pack(anchor='w', pady=(10, 0))
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=8)
        ttk.Entry(row, textvariable=folder).pack(side='left', fill='x', expand=True, padx=(0, 10))
        def browse():
            selected = filedialog.askdirectory(parent=root, title='Escolha a pasta sincronizada do Google Drive')
            if selected:
                folder.set(selected)
        ttk.Button(row, text='Escolher pasta', command=browse).pack(side='right')
        ttk.Label(frame, text='O principal e o Universal OS precisam estar abertos. Se abrir após o horário,\na cópia pendente do dia será feita. São mantidas as últimas 30 cópias automáticas.\nInclui OS, numeração e usuários com senhas protegidas.\nO envio depende do Google Drive conectado e sincronizando.', wraplength=680).pack(anchor='w', pady=10)
        def refresh():
            value = scheduler.status()
            state.set(('Última cópia criada: ' + value['last_success'].replace('T', ' ') if value['last_success'] else 'Nenhuma cópia automática criada ainda.') +
                      ('\n' + value['error'] if value['error'] else ''))
            root.after(15000, refresh)
        ttk.Label(frame, textvariable=state, wraplength=680).pack(anchor='w', pady=10)
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x', pady=12)
        results = queue.SimpleQueue()
        def check_results():
            try:
                result = results.get_nowait()
            except queue.Empty:
                pass
            else:
                now_button.configure(state='normal')
                messagebox.showinfo('Backup', result, parent=root)
            root.after(300, check_results)
        def save(run=False):
            try:
                authorize()
                scheduler.configure(enabled.get(), folder.get().strip(), scheduled.get().strip())
                if run:
                    def worker():
                        try:
                            scheduler.run_now()
                            result = 'Cópia criada na pasta escolhida. Confira a sincronização no Google Drive.'
                        except Exception as error:
                            result = 'Não foi possível criar a cópia: ' + str(error)
                        results.put(result)
                    now_button.configure(state='disabled')
                    threading.Thread(target=worker, daemon=True).start()
                else:
                    messagebox.showinfo('Backup', 'Configuração salva. ' + ('Backup diário às ' + scheduled.get() + '.' if enabled.get() else 'Backup automático desativado.'), parent=root)
            except Exception as error:
                messagebox.showerror('Confira o backup', str(error), parent=root)
        ttk.Button(buttons, text='Salvar configuração', command=save).pack(side='left', padx=(0, 10))
        now_button = ttk.Button(buttons, text='Fazer backup agora', command=lambda: save(True))
        now_button.pack(side='left')
        ttk.Button(buttons, text='Fechar', command=root.destroy).pack(side='right')
        refresh()
        check_results()
        root.mainloop()
    finally:
        if root:
            try:
                root.destroy()
            except tk.TclError:
                pass
        DIALOG_LOCK.release()
