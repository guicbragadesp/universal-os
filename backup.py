"""Cópia consistente do banco, inclusive com o servidor em uso."""
import argparse
from contextlib import closing
import datetime
from pathlib import Path
import sqlite3
import server

parser = argparse.ArgumentParser()
parser.add_argument('--destination', help='Pasta de backup; padrão: data/backups')
args = parser.parse_args()
if not server.DB.exists():
    raise SystemExit('Banco ainda não existe. Inicie o programa primeiro.')
destination = Path(args.destination) if args.destination else server.DATA / 'backups'
destination.mkdir(parents=True, exist_ok=True)
target = destination / ('universal-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
with closing(sqlite3.connect(server.DB)) as source, closing(sqlite3.connect(target)) as output:
    source.backup(output)
print('Backup concluído: ' + str(target))
