# Universal OS — versão inicial 1.0

**Atualização 1.1:** há um instalador Windows independente, `Instalar-Universal-OS-1.1.exe`. Ele inclui o Python necessário e oferece modos principal e cliente. Para essa versão, siga `INSTALAR-EM-REDE.txt`. No principal, o banco fica em `%LOCALAPPDATA%\UniversalOS\data`, e não na pasta do programa. O instalador é para Windows 10/11 x64. As instruções Python abaixo continuam válidas apenas para executar o código-fonte original.

Sistema central de ordens de serviço para o Despachante Universal. Esta entrega é um programa funcional para rede local, com arquivos de instalação para servidor na nuvem. **Ainda não está hospedado na internet.**

## Começar no escritório

1. Escolha um computador atual para ser o servidor, com Python 3.10 ou superior instalado. Mantenha esse computador ligado enquanto a equipe usa o sistema.
2. Extraia a pasta inteira e abra `Iniciar.cmd`. A janela mostra um código de configuração, necessário apenas para criar o primeiro administrador.
3. Nesse computador, abra `http://localhost:8765`. Preencha o código, seu nome, usuário e senha (mínimo de 10 caracteres). Depois entre com esse usuário e senha.
4. Em **Configurações**, confira o próximo número (inicialmente **40952**) e cadastre cada funcionário com nome e acesso individuais. Não há senha padrão.
5. Nos demais PCs, abra `http://IP-DO-SERVIDOR:8765`. Consulte o IP do servidor com `ipconfig`. Se necessário, libere a porta TCP 8765 somente na rede privada do Windows. Não exponha essa porta diretamente na internet.

Cada navegador exige login. Use **Sair** em computadores compartilhados. Senhas são armazenadas com PBKDF2-SHA256 e sal individual; não ficam em texto legível. A sessão dura até 8 horas. Alguns navegadores restauram cookies de sessão quando restauram janelas; por isso Sair é necessário ao trocar de pessoa.

## Usar as OS

- Clique em **Nova ordem de serviço**, preencha cliente, veículo e valores. Os sete serviços do formulário vêm com valor zero, sem reaproveitar valores de outra OS. Edite, remova ou adicione linhas com **+ Adicionar serviço** (até 500 linhas).
- O número é atribuído no primeiro salvamento, em transação no banco central. Salvar novamente ou reimprimir mantém o número. Repetir a mesma requisição após falha de rede não cria outra OS.
- Busque por placa, número exato ou nome do cliente. Abra a OS para alterar ou reimprimir. Se outra pessoa editar a mesma OS ao mesmo tempo, o sistema pede para reabri-la antes de salvar, evitando sobrescrever a edição.
- O total soma os serviços; o saldo desconta o pagamento. Pagamento maior que o total é rejeitado.
- Em **Configurações**, o administrador altera a próxima numeração. Ela precisa ser maior que todos os números já usados. Isso preserva as OS existentes e evita futuras repetições.
- O histórico identifica quem criou e alterou a OS. Funcionários acessam os registros do escritório; somente administradores gerenciam usuários, numeração e exportação.

## Imprimir e salvar PDF

Salve a OS e clique em **Imprimir / PDF**. Use papel A4, escala 100% e desative os cabeçalhos e rodapés do navegador. Para PDF, escolha **Salvar como PDF** na janela de impressão.

O formulário foi redesenhado a partir do seu arquivo: cabeçalho, contato, dados, discriminação, valor, total, pagamento e saldo. A referência é uma digitalização de tamanho incomum (243 × 426 mm); esta versão adapta suas proporções para A4. Fontes e aparência não são uma reprodução pixel a pixel do papel digitalizado. Mais de 19 serviços geram continuação com o mesmo número; os totais aparecem apenas ao final. Na versão 1.2, observações são impressas em vermelho abaixo dos totais; textos longos podem continuar na página seguinte. O carimbo PAGO é opcional e exige total positivo com saldo zerado.

## Windows 7

O servidor deve usar um sistema operacional atual. Os PCs com Windows 7 podem tentar acessar pelo navegador da rede; **esta combinação ainda não foi testada e não tem garantia de compatibilidade**. A interface não exige instalar um aplicativo nesses PCs. Não instale navegadores antigos para contornar incompatibilidade.

## Backup e recuperação

**Não há backup automático configurado nesta entrega.**

- Abra `Backup.cmd` diariamente. Ele cria uma cópia consistente em `data/backups`, mesmo com o sistema aberto. Copie o arquivo para um local separado e privado. Uma cópia no mesmo disco não protege contra perda do computador.
- Para pasta externa, use `python backup.py --destination "D:\BackupUniversal"`. Esse comando pode ser agendado no Agendador de Tarefas do Windows ou no serviço da futura hospedagem.
- A opção **Baixar registros** exporta OS e histórico em JSON. Não contém senhas e não substitui o backup completo do SQLite.
- Para restaurar um backup completo: encerre o servidor; preserve a pasta `data` atual; restaure em uma pasta `data` vazia uma cópia do backup com nome `universal.sqlite3`; inicie o programa. Não misture o banco restaurado com arquivos antigos `-wal` ou `-shm`. Sessões antigas expiram em até 8 horas; para revogá-las imediatamente, um técnico pode executar `DELETE FROM sessions` no banco restaurado antes de reiniciar.
- O banco contém informações de clientes e hashes de senhas. Restrinja acesso à pasta e às cópias de segurança.

## Hospedar na nuvem

Como ainda não existe uma hospedagem definida, nenhuma conta foi criada e nenhum dado foi publicado. O Dockerfile permite instalar em um servidor com Python/Docker, mas a configuração deve incluir:

1. HTTPS com certificado e domínio; proxy encaminhando para a porta 8765.
2. Volume persistente montado em `/data`, pertencente ao UID 10001. Sem esse volume, as OS seriam perdidas ao substituir o contêiner.
3. Variável `OS_HTTPS=1`, para cookies seguros. Opcionalmente `OS_SETUP_TOKEN` secreto no primeiro acesso; se omitido, o código aparece no log privado do servidor. Não publique esse código.
4. Uma única instância do aplicativo e do banco. Não distribuir cópias do SQLite entre servidores. Vários funcionários podem usar essa instância simultaneamente.
5. Backup diário do volume/banco, retenção e teste de restauração. A hospedagem não fornece esse backup automaticamente só por usar o Dockerfile.

Exemplo de construção: `docker build -t universal-os .`. O responsável pela hospedagem deve configurar volume, HTTPS, reinício e backup antes de liberar o endereço para a equipe. O servidor HTTP incluído atende escritórios pequenos; a implantação online precisa de proxy com limites e monitoramento.

Nenhuma alteração foi publicada no repositório anterior do Braga: este é um sistema separado de OS. Nenhuma consulta aos portais de veículos ou pagamento é feita por este programa.
