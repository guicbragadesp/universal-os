"""Validated full database recovery, serialized with all application connections."""
import datetime
import json
from pathlib import Path
import sqlite3
import tempfile
from contextlib import closing
import server

REQUIRED = {
 'users': {'id','username','name','password','admin','active','created_at'},
 'orders': {'id','number','request_key','date','name','phone','vehicle','plate','items','paid','total','notes','version','created_by','updated_by','created_at','updated_at'},
 'settings': {'id','next_number'},
 'audit': {'id','order_id','actor','action','at','snapshot'},
 'sessions': {'token','user_id','csrf','expires'},
}

def inspect_backup(database):
    with closing(sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True)) as c:
        if c.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('O arquivo está danificado. Escolha outra cópia.')
        for table, required in REQUIRED.items():
            columns = {r[1] for r in c.execute('PRAGMA table_info('+table+')')}
            if not required <= columns:
                raise ValueError('Este arquivo não é um backup completo compatível do Universal OS.')
        if c.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('O backup contém vínculos inválidos.')
        if not c.execute('SELECT 1 FROM users WHERE active=1 AND admin=1').fetchone():
            raise ValueError('O backup não possui administrador ativo para entrar após a recuperação.')
        setting = c.execute('SELECT next_number FROM settings WHERE id=1').fetchone()
        maximum = c.execute('SELECT COALESCE(MAX(number),0) FROM orders').fetchone()[0]
        if not setting or not isinstance(setting[0],int) or setting[0]<=maximum:
            raise ValueError('A numeração do backup é inválida.')
        return {'orders':c.execute('SELECT COUNT(*) FROM orders').fetchone()[0], 'next_number':setting[0]}

def copy_database(source, destination):
    source_connection = sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True,timeout=30)
    output = sqlite3.connect(destination,timeout=30)
    try:
        source_connection.backup(output)
    finally:
        output.close()
        source_connection.close()

def recover(selected, authorize, confirm):
    """Callbacks are native authorization and explicit full-replacement confirmation."""
    authorize()
    selected = Path(selected).resolve(strict=True)
    if selected == server.DB.resolve():
        raise ValueError('Selecione uma cópia de backup, não o banco em uso.')
    if selected.suffix.lower() != '.sqlite3':
        raise ValueError('Escolha o backup completo .sqlite3. A exportação JSON não serve para recuperação completa.')
    # Snapshot first: cloud files may change while a confirmation is open.
    with tempfile.TemporaryDirectory(prefix='UniversalOS-recuperar-',dir=server.DATA.parent) as temporary:
        staged = Path(temporary)/'validated.sqlite3'
        copy_database(selected,staged)
        info = inspect_backup(staged)
        server.initialize(staged)
        inspect_backup(staged)
        with closing(sqlite3.connect(staged)) as c:
            c.execute('DELETE FROM sessions')
            c.execute('DELETE FROM login_attempts')
            c.execute('INSERT INTO audit(actor,action,at,snapshot) VALUES(NULL,?,?,?)',
                      ('recuperou backup completo',server.now(),json.dumps(info)))
            c.commit()
        if not confirm(info):
            return None
        authorize()
        with server.DATABASE_LOCK:
            folder = server.DATA/'backups-antes-recuperacao'
            folder.mkdir(exist_ok=True)
            safety = folder/('UniversalOS-antes-recuperacao-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
            copy_database(server.DB,safety)
            with closing(sqlite3.connect(safety)) as c:
                if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                    raise ValueError('Não foi possível validar a cópia de segurança atual. Nada foi restaurado.')
            # SQLite backup replaces the destination in one transaction; failures roll back.
            copy_database(staged,server.DB)
            return {'safety':str(safety),**info}
