# Universal OS

Sistema de ordens de serviço do Despachante Universal, para rede local e Windows 10/11 de 64 bits.

## Instalar

[Baixar instalador Windows](https://github.com/guicbragadesp/universal-os/releases/latest)

Escolha **Computador principal** em um único PC. Nos demais escolha **Acesso pela rede**, informando o endereço mostrado no principal. Cada funcionário entra com usuário e senha próprios. O principal precisa ficar ligado com o programa aberto. O sistema ainda não está hospedado na nuvem.

## Atualizações

A partir da versão 1.9, o aplicativo verifica novas versões ao abrir e a cada 6 horas enquanto estiver aberto. Há também **Programa → Buscar atualização** no menu da janela.

Se existir uma versão mais recente, o usuário recebe um aviso e decide quando baixar e abrir o instalador. Salve alterações antes de aceitar. O tamanho e o SHA-256 do download são conferidos; o principal cria uma cópia consistente do banco antes de abrir o instalador. Sem internet o uso na rede local continua. A primeira instalação da versão 1.9 ainda precisa ser feita manualmente.

O catálogo público é `latest.json`; os instaladores ficam nos Releases deste repositório. Novas versões só ficam disponíveis quando forem publicadas aqui. O aplicativo não envia registros de clientes ao GitHub.

## Dados privados

As OS ficam no principal em `%LOCALAPPDATA%\UniversalOS\data`. Esse banco, senhas, sessões e backups **não fazem parte deste repositório**. Use o mesmo usuário Windows no principal para manter o acesso aos registros. Não remova essa pasta ao atualizar. Faça também backups externos; o backup criado durante atualização fica no mesmo computador.

## Executar o código

Python 3.10 ou superior. O servidor não tem dependências externas; a janela desktop requer `pip install -r requirements-desktop.txt`:

```text
python desktop.py
```

Nos clientes: `python desktop.py --cliente`. Para servidor sem janela: `python server.py --host 0.0.0.0 --port 8765`. Na janela do computador principal, o primeiro administrador é criado diretamente com nome, usuário e senha; não há senha padrão. No servidor sem janela, use o código exibido no terminal.

## Compilar

Instale PyInstaller em um ambiente de desenvolvimento Windows e execute, na raiz:

```text
python -m PyInstaller --onefile --windowed --name Universal-OS --icon public/icon.ico --collect-all webview --collect-all pythonnet --collect-all clr_loader --add-data "public;public" desktop.py
```

Compile `installer.iss` com Inno Setup. O arquivo está configurado para esta versão. Para uma nova versão, atualize `updater.VERSION`, os nomes versionados do instalador/executável e os processos anteriores a encerrar. Publique o instalador nos Releases antes de atualizar `latest.json` com sua versão, URL, tamanho exato e SHA-256. Nunca inclua dados de produção no pacote.

## Impressão

Papel A4, escala 100%, cabeçalhos e rodapés do navegador desativados. O nome sugerido do PDF é `PLACA - OS NUMERO.pdf`. O carimbo PAGO exige pagamento integral. Os campos Nome, Telefone, Veículo e Placa têm o destaque definido para impressão; a tela de digitação conserva seu estilo.

## Versão 1.10

**Imprimir / PDF** salva novas OS e alterações automaticamente antes de abrir a impressão. **Salvar** apenas salva, sem imprimir. Se houver dados inválidos, conflito de edição ou erro no salvamento, a impressão não abre. Reimprimir mantém o número da OS.

## Versão 1.11

Impressão em duas vias na mesma folha A4: cliente em cima, escritório embaixo. Escolha ambas, só cliente ou só escritório. Cada via mantém 135 mm de altura e a mesma posição; a outra metade fica em branco quando não selecionada. Textos extensos continuam em outras folhas sem reduzir a fonte ou cortar dados. Linhas finas em cinza.

Marcar PAGO preenche o pagamento até o total da OS, incluindo o restante de pagamentos parciais. Desmarcar remove o carimbo sem apagar o pagamento. O banco continua exigindo quitação para salvar o carimbo.

## Versão 1.12 — janela própria

A interface abre em janela integrada do aplicativo, sem abas ou barra de endereço do Chrome. O controle do principal permanece aberto para atender a rede e oferecer backup e atualização. Os clientes guardam o endereço do principal após a primeira configuração. Cada nova janela usa sessão privada e pede login.

Senhas novas de 4 a 10 caracteres são aceitas no cadastro, troca e redefinição, sem composição obrigatória. Senhas antigas, inclusive mais longas, continuam aceitas no login.

O instalador verifica o Microsoft WebView2 Runtime e instala o bootstrapper oficial somente se necessário. Nesse caso precisa de internet. Para recompilar, execute `download-webview2.ps1` antes de compilar `installer.iss`. O bootstrapper é conferido pela assinatura Microsoft e não é publicado no código-fonte; ele faz parte do instalador. Não altera registros ou senhas existentes.

## Versão 1.13 — uma única janela e recuperação de senha

O principal inicia o servidor e a interface no mesmo processo, com uma única janela. O menu **Programa** reúne atualização, informações da rede e backup completo (exige login de administrador). Ao fechar a janela do principal, a rede deixa de atender até reabrir. Nos clientes, o endereço já salvo abre diretamente a janela de trabalho; para mudar o IP, use **Configurar rede do Universal OS** no menu Iniciar.

**Minha senha** permite trocar a senha atual. Em **Configurações → Equipe**, o administrador redefine senhas de outros usuários. Em **Configurações → Recuperação da sua senha**, cada administrador pode gerar seu próprio código, confirmando a senha atual. Guarde-o em local privado: ele só aparece ao gerar, e cada novo código invalida o anterior. No login, **Esqueci minha senha** aceita usuário, código e nova senha. O código é consumido após o uso e encerra as sessões anteriores desse administrador; gere outro após entrar novamente. O banco guarda apenas o hash do código e os registros de auditoria não contêm o código. Sem código guardado, peça a outro administrador para redefinir sua senha.


NOVIDADES 1.14 — ENDEREÇO COPIÁVEL E BACKUP DIÁRIO
Menu Programa > Informações da rede: endereço selecionável, Ctrl+C e botão Copiar endereço.
No principal, entre como administrador e use Programa > Backup automático — Google Drive.
Escolha uma pasta já sincronizada pelo Google Drive para computador, marque Ativar e salve.
O horário inicial é 17:30, no relógio deste computador, e pode ser alterado.
O backup inclui todas as OS, numeração, usuários e senhas protegidas, usando cópia consistente do SQLite.
Mantenha o principal e o Universal OS abertos. Ao abrir depois do horário, será feita a cópia pendente do dia.
Cada instalação mantém uma subpasta própria e as últimas 30 cópias automáticas. Backups manuais ficam separados.
A cópia é verificada antes de ser concluída. Se a pasta estiver indisponível, tenta novamente em cinco minutos.
A tela mostra a última cópia criada e eventuais falhas. Fazer backup agora permite conferir o destino.
O programa confirma a criação local do arquivo; o envio à nuvem depende do Google Drive conectado e sincronizando.
O backup começa desativado até você escolher a pasta e salvar a configuração no computador principal.
Não é preciso configurar nos PCs clientes. A atualização preserva o banco e as configurações existentes.
