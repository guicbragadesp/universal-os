# Universal OS

Sistema de ordens de serviço do Despachante Universal, para rede local e Windows 10/11 de 64 bits.

## Instalar

[Baixar instalador Windows](https://github.com/guicbragadesp/universal-os/releases/latest)

Escolha **Computador principal** em um único PC. Nos demais escolha **Acesso pela rede**, informando o endereço mostrado no principal. Cada funcionário entra com usuário e senha próprios. O principal precisa ficar ligado com o programa aberto. O sistema ainda não está hospedado na nuvem.

## Atualizações

A partir da versão 1.9, o aplicativo verifica novas versões ao abrir e a cada 6 horas enquanto estiver aberto. Há também o botão **Buscar atualização** na janela do programa.

Se existir uma versão mais recente, o usuário recebe um aviso e decide quando baixar e abrir o instalador. Salve alterações antes de aceitar. O tamanho e o SHA-256 do download são conferidos; o principal cria uma cópia consistente do banco antes de abrir o instalador. Sem internet o uso na rede local continua. A primeira instalação da versão 1.9 ainda precisa ser feita manualmente.

O catálogo público é `latest.json`; os instaladores ficam nos Releases deste repositório. Novas versões só ficam disponíveis quando forem publicadas aqui. O aplicativo não envia registros de clientes ao GitHub.

## Dados privados

As OS ficam no principal em `%LOCALAPPDATA%\UniversalOS\data`. Esse banco, senhas, sessões e backups **não fazem parte deste repositório**. Use o mesmo usuário Windows no principal para manter o acesso aos registros. Não remova essa pasta ao atualizar. Faça também backups externos; o backup criado durante atualização fica no mesmo computador.

## Executar o código

Python 3.10 ou superior. Sem dependências externas para o servidor:

```text
python desktop.py
```

Nos clientes: `python desktop.py --cliente`. Para servidor sem janela: `python server.py --host 0.0.0.0 --port 8765`. O primeiro administrador é criado com o código exibido pelo programa; não há senha padrão.

## Compilar

Instale PyInstaller em um ambiente de desenvolvimento Windows e execute, na raiz:

```text
python -m PyInstaller --onefile --windowed --name Universal-OS --icon public/icon.ico --add-data "public;public" desktop.py
```

Compile `installer.iss` com Inno Setup. O arquivo está configurado para esta versão. Para uma nova versão, atualize `updater.VERSION`, os nomes versionados do instalador/executável e os processos anteriores a encerrar. Publique o instalador nos Releases antes de atualizar `latest.json` com sua versão, URL, tamanho exato e SHA-256. Nunca inclua dados de produção no pacote.

## Impressão

Papel A4, escala 100%, cabeçalhos e rodapés do navegador desativados. O nome sugerido do PDF é `PLACA - OS NUMERO.pdf`. O carimbo PAGO exige pagamento integral. Os campos Nome, Telefone, Veículo e Placa têm o destaque definido para impressão; a tela de digitação conserva seu estilo.

## Versão 1.10

**Imprimir / PDF** salva novas OS e alterações automaticamente antes de abrir a impressão. **Salvar** apenas salva, sem imprimir. Se houver dados inválidos, conflito de edição ou erro no salvamento, a impressão não abre. Reimprimir mantém o número da OS.

## Versão 1.11

Impressão em duas vias na mesma folha A4: cliente em cima, escritório embaixo. Escolha ambas, só cliente ou só escritório. Cada via mantém 135 mm de altura e a mesma posição; a outra metade fica em branco quando não selecionada. Textos extensos continuam em outras folhas sem reduzir a fonte ou cortar dados. Linhas finas em cinza.

Marcar PAGO preenche o pagamento até o total da OS, incluindo o restante de pagamentos parciais. Desmarcar remove o carimbo sem apagar o pagamento. O banco continua exigindo quitação para salvar o carimbo.
