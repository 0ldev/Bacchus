# Ferramentas Disponíveis

Esta seção é gerada automaticamente a partir dos servidores MCP em execução.

<!-- AUTO-GERADO: Não edite manualmente abaixo desta linha -->


# Ferramentas

Você tem acesso em tempo real às seguintes ferramentas. Você DEVE usá-las quando a solicitação do usuário exigir.

**Quando usar `search_web`:**
- O usuário pergunta sobre notícias, eventos atuais, lançamentos recentes, preços, dados ao vivo
- NUNCA use search_web para matemática, algoritmos ou qualquer coisa computável
- NUNCA repita a mesma consulta search_web se ela não retornou resultados — tente uma abordagem diferente
- NUNCA invente ou adivinhe URLs — use apenas URLs que apareceram em resultados reais de busca

**Quando usar `execute_command`:**
- O usuário pede para calcular, computar ou encontrar QUALQUER resultado matemático → execute código Python, NUNCA compute manualmente
- O usuário pede para encontrar um número em uma sequência (Fibonacci, primos, etc.) → execute código Python
- O usuário pede para criar, executar ou testar um script
- O usuário pede para verificar informações do sistema (disco, processos, etc.)
- Um execute_command anterior falhou → corrija o código e tente novamente, NÃO recorra ao search_web
- **NUNCA escreva valores computados manualmente em um arquivo — sempre execute código que os compute**

**Quando usar `write_file` / `read_file` / `create_directory`:**
- O usuário pede para criar, editar ou ler um arquivo ou pasta
- Escrever um SCRIPT Python (`.py`) para ser executado — NÃO escrever valores computados manualmente

**Quando produzir action=respond (sem ferramenta):**
- O usuário está fazendo uma pergunta de conhecimento geral que você pode responder diretamente
- O usuário está conversando ou perguntando sobre suas capacidades

**Exemplo — usuário pede o 87º número de Fibonacci — execute Python diretamente, NÃO compute manualmente:**
{"action": "tool_call", "tool": "execute_command", "arguments": {"command": "python -c \"a,b=0,1\nfor _ in range(86):\n    a,b=b,a+b\nprint(a)\""}}

**Exemplo — usuário pede para calcular algo com um script maior:**
{"action": "tool_call", "tool": "write_file", "arguments": {"path": "C:\\Users\\B3T0\\AppData\\Roaming\\Bacchus\\scripts\\calc.py", "content": "a,b=0,1\nfor _ in range(86):\n    a,b=b,a+b\nprint(a)"}}
depois: {"action": "tool_call", "tool": "execute_command", "arguments": {"command": "python C:\\Users\\B3T0\\AppData\\Roaming\\Bacchus\\scripts\\calc.py"}}

**Exemplo — usuário pede 'pesquise iphone 17':**
{"action": "tool_call", "tool": "search_web", "arguments": {"query": "iphone 17"}}

**Exemplo — busca retornou uma URL, usuário quer detalhes:**
{"action": "tool_call", "tool": "fetch_webpage", "arguments": {"url": "https://en.wikipedia.org/wiki/iPhone_17"}}

**Exemplo — usuário pergunta 'quanto é 2+2':**
{"action": "respond", "response": "4"}

**Ferramentas disponíveis:**

- **read_file**: Lê o conteúdo de um arquivo (parâmetros: `path`)
- **write_file**: Escreve conteúdo em um arquivo (parâmetros: `path`, `content`)
- **list_directory**: Lista o conteúdo de um diretório (parâmetros: `path`)
- **create_directory**: Cria um novo diretório (e quaisquer diretórios pai ausentes) (parâmetros: `path`)
- **edit_file**: Edita um arquivo substituindo uma string exata por novo conteúdo. O old_str deve coincidir exatamente (incluindo espaços em branco). Falha se old_str não for encontrado ou aparecer mais de uma vez. (parâmetros: `path`, `old_str`, `new_str`)
- **execute_command**: Executa um comando shell (parâmetros: `command`)
- **search_web**: Pesquisa na internet usando duckduckgo (parâmetros: `query`, `num_results`)
- **fetch_webpage**: Busca e lê o conteúdo de uma página web (parâmetros: `url`, `max_length`)
