# Repo Studio

Editor visual para gerir o `repo.json` de `repo.serloko.com` e importar apps de outros catálogos iOS. A saída usa a estrutura AltStore/SideStore (`name`, `identifier` e `apps` com `versions`).

## Executar no VS Code

1. Abre esta pasta no VS Code.
2. Instala a extensão **Live Server** (Ritwick Dey), se ainda não estiver instalada.
3. Abre `index.html` e seleciona **Go Live** na barra de estado, ou clica com o botão direito no ficheiro e escolhe **Open with Live Server**.
4. O site tenta carregar automaticamente o `repo.json` que está ao lado do `index.html`. Se não o encontrar, usa **Abrir meu repo.json** para selecionar o ficheiro atual.
5. Na área **Importar catálogo**, carrega por URL, ficheiro `.json` ou conteúdo colado. **Experimentar exemplo** permite testar sem ligação à Internet.
6. Seleciona apps do catálogo e clica **Adicionar selecionadas ao meu repo**. Apps com o mesmo bundle identifier (ou nome, se não houver identificador) são ignoradas, nunca substituídas. A lista **Apps no meu repo.json** permite editar ou remover apps existentes.
7. Clica **Gerar repo.json atualizado**, revê o resultado e descarrega `repo.json`. Publica o ficheiro atualizado no GitHub junto ao `index.html` para o site o carregar na próxima visita.

Também podes abrir `index.html` diretamente no navegador para trabalhar com ficheiros locais e com a demonstração. Para importar URLs externos, usa o Live Server ou outro servidor local; o navegador pode bloquear alguns pedidos por CORS. Quando isso acontecer, podes optar por tentar o proxy público AllOrigins, após uma confirmação. O URL do repositório é partilhado com esse serviço; não uses o proxy para URLs privados ou sensíveis. Em alternativa, descarrega o JSON e abre-o localmente ou cola o conteúdo no campo manual.

O projeto não precisa de Node.js, dependências ou etapa de compilação. As alterações são um rascunho local e não são gravadas diretamente no GitHub: um site estático não pode alterar os ficheiros do repositório sem um backend ou autenticação. Descarrega o `repo.json` e publica-o/commita-o no GitHub. As apps existentes, os campos JSON adicionais e o histórico de versões são preservados; a exportação é orientada ao padrão AltStore/SideStore.