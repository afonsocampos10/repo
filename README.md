# repo.serloko.com

O site público mostra apenas `OK`. O catálogo continua disponível em
[`repo.json`](./repo.json), na raiz do site.

## Abrir o editor local

O editor está em `.vscode/repo-editor.html` e não faz parte do site público.
Para o executar:

1. Abre esta pasta no VS Code.
2. Executa **Tasks: Run Task** na paleta de comandos.
3. Seleciona **Executar editor local do repo**.
4. Abre <http://127.0.0.1:8000/.vscode/repo-editor.html> no navegador.

A tarefa liga o servidor apenas a `127.0.0.1`, pelo que não fica acessível
através da rede. É necessário ter Python 3 instalado. Para terminar, pára a
tarefa no terminal do VS Code com `Ctrl+C`.

O editor carrega o `repo.json` local da raiz. Quando terminares, gera e
descarrega o JSON atualizado, substitui o ficheiro `repo.json` da raiz por
esse ficheiro e publica as alterações normalmente. O editor não escreve
diretamente no GitHub.
