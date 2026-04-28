# VozAssistente

Assistente pessoal por voz **100% local** para Windows, em português brasileiro.
Roda em segundo plano, escuta comandos pelo microfone, interpreta intents,
executa ações no PC e responde por voz.

> **Status:** versão 1.0 — base funcional pronta. Estrutura preparada para
> evoluir com wake word, LLM local (Ollama) e automações mais complexas.

---

## Para usuários finais (instalação rápida)

> Não precisa de Python, nem de conhecimento técnico.

1. Vá para a página de **[Releases](https://github.com/XxMexicanoXx/projeto-servus/releases)** do projeto.
2. Baixe `VozAssistente-Setup-1.0.0.exe` (em **Assets**).
3. Execute o instalador — wizard padrão Windows em pt-BR.
   - Escolha se quer atalho na Área de Trabalho e/ou iniciar com o Windows.
4. Após instalar, o app já abre. Você ouvirá **"Assistente pronto."** e verá
   um ícone de microfone na bandeja do sistema (canto inferior direito,
   próximo ao relógio).
5. Fale comandos como "que horas são", "abrir bloco de notas", "criar pasta
   chamada teste" — veja a [lista completa abaixo](#comandos-suportados-exemplos).

**Configuração:** Menu Iniciar → "VozAssistente (Editar configuração)" — abre
o `config.json` no Notepad. Lá você muda o caminho do Chrome/Spotify para
combinar com sua máquina.

> 💡 **Não há binário pronto ainda?** Veja a seção
> [Gerando o instalador via GitHub Actions](#gerando-o-instalador-via-github-actions)
> ou rode `build_installer.bat` localmente.

---

## Recursos

- **STT offline** com [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) (modelo configurável: `tiny`/`base`/`small`/`medium`)
- **TTS offline neural** via [Piper TTS](https://github.com/rhasspy/piper) (voz pt-BR masculina natural — `faber`); cai automaticamente para `pyttsx3`/SAPI5 se Piper falhar
- **Onboarding** no primeiro uso pergunta o nome do usuário e usa nas saudações ("Olá Nicolas!"). Para mudar depois, fale "mude meu nome para X"
- **VAD por energia** (RMS) com pré-roll — captura frases naturalmente, sem hotkey
- **Intents determinísticos** (regex) com ponto de extensão para LLM local
- **System tray** com menu (status, pausar/retomar escuta, sair)
- **Threads não-bloqueantes** — fala enquanto continua escutando
- **Configuração via `config.json`** — sem caminhos hardcoded
- **Logs rotativos** em `%LOCALAPPDATA%\VozAssistente\logs\`
- **Empacotamento `.exe` via PyInstaller** (um único arquivo)

---

## Estrutura

```
voz-assistente/
├── assistant/
│   ├── main.py              # Orquestração + system tray + CLI
│   └── config.json          # Configuração (caminhos de programas, flags)
├── modules/
│   ├── audio_input.py       # Microfone + VAD por RMS
│   ├── speech_to_text.py    # Wrapper faster-whisper
│   ├── intent_parser.py     # Regras + hook p/ LLM
│   ├── action_executor.py   # Abrir/fechar/criar/mover, shutdown, web, etc.
│   └── text_to_speech.py    # Fila pyttsx3 não-bloqueante
├── utils/
│   ├── logger.py            # Logging rotativo
│   └── config.py            # Loader/merge do config.json
├── requirements.txt
├── assistant.spec           # PyInstaller
├── build.bat                # Script de build (.exe)
└── README.md
```

---

## Instalação (modo dev)

> Requer Python 3.10+ (recomendado 3.11). No primeiro `import faster-whisper`,
> o modelo é baixado automaticamente para o cache do usuário (~244 MB para `small`).

```powershell
git clone https://github.com/<seu-usuario>/voz-assistente.git
cd voz-assistente

python -m venv .venv
.\.venv\Scripts\activate

pip install -r requirements.txt

python -m assistant.main
```

Para listar os microfones disponíveis e descobrir o `device_index`:

```powershell
python -m assistant.main --list-devices
```

---

## Build do executável (.exe)

No Windows, com o repo já clonado:

```cmd
build.bat
```

Saída: `dist\VozAssistente.exe` (+ `dist\config.json` ao lado, editável).
Build manual:

```powershell
.\.venv\Scripts\activate
pyinstaller assistant.spec --clean --noconfirm
```

> **Tamanho do .exe:** ~150–250 MB (depende do modelo Whisper e do `ctranslate2`).
> Para reduzir, use `compute_type: "int8"` (default) e `model_size: "tiny"` ou `"base"`.

---

## Pacote de instalação (.exe instalável)

Para distribuir aos usuários finais, o repo já vem com um script
[Inno Setup](https://jrsoftware.org/isinfo.php) que empacota o `.exe` num
**instalador padrão Windows** (`VozAssistente-Setup-1.0.0.exe`).

**Pré-requisito (uma vez):** instale o
[Inno Setup 6](https://jrsoftware.org/isdl.php) — aceita o local default
`C:\Program Files (x86)\Inno Setup 6`.

Build de tudo (PyInstaller + instalador) com um comando:

```cmd
build_installer.bat
```

Saída: `installer_output\VozAssistente-Setup-1.0.0.exe`.

O instalador faz:

- Instala em `%ProgramFiles%\VozAssistente\` (sem privilégios de admin —
  `lowest`; promove para admin se o usuário escolher "All Users")
- Cria atalho no **Menu Iniciar**
- (Opcional) Atalho na **Área de Trabalho**
- (Opcional) **Iniciar com o Windows** (entrada em `shell:startup`)
- Cria entrada **"VozAssistente (Editar configuração)"** no Menu Iniciar que
  abre `%APPDATA%\VozAssistente\config.json` no Notepad
- Copia o `config.json` padrão para `%APPDATA%\VozAssistente\config.json`
  **somente se ainda não existir** — sua personalização não é sobrescrita em
  upgrades
- Registra um **desinstalador** acessível em
  *Configurações → Apps → VozAssistente*

**Hierarquia de busca do config (após instalado):**

1. `%APPDATA%\VozAssistente\config.json` ← editável; é o que o instalador grava
2. `<pasta do .exe>\config.json` (modo portátil)
3. `<pasta do .exe>\assistant\config.json` (modo dev)
4. Default embutido

Para mudar a versão do instalador, edite `MyAppVersion` no topo de
[`installer.iss`](installer.iss).

---

## Gerando o instalador via GitHub Actions

O repo tem um workflow ([`.github/workflows/release.yml`](.github/workflows/release.yml))
que **compila o instalador automaticamente em runner Windows** e disponibiliza
o `.exe` para download. Útil quando você não tem Windows à mão.

### Opção 1 — Build manual (qualquer hora)

1. Vá em **Actions → Build Windows Installer**
2. Clique em **Run workflow** (canto direito) → **Run workflow**
3. Aguarde ~5–10 min
4. Quando terminar, clique no run mais recente → role até **Artifacts** →
   baixe `VozAssistente-Setup-1.0.0.zip` (contém o `.exe` + `SHA256SUMS.txt`)

### Opção 2 — Release oficial (com tag)

```bash
git tag v1.0.0
git push origin v1.0.0
```

O workflow detecta o tag `v*`, compila o instalador, **cria uma Release no
GitHub** automaticamente e anexa o `.exe` como asset (acessível publicamente
em `https://github.com/<usuario>/<repo>/releases`). Isso é o que usuários
finais baixam.

---

## Configuração (`config.json`)

Procurado em (na ordem):

1. `--config <caminho>` na linha de comando
2. `VOZ_ASSISTENTE_CONFIG` (variável de ambiente)
3. `<diretório do .exe>\config.json` (modo empacotado — recomendado)
4. `assistant/config.json` (modo dev)

Campos principais:

| Campo                              | Descrição                                                                |
| ---------------------------------- | ------------------------------------------------------------------------ |
| `general.start_listening_on_launch`| Começar escutando ao abrir                                               |
| `general.exit_phrases`             | Frases que encerram o assistente                                         |
| `audio.device_index`               | Índice do microfone (`null` = padrão do SO)                              |
| `audio.silence_threshold_rms`      | Limiar de silêncio (0–1). Aumente em ambientes com ruído                 |
| `stt.model_size`                   | `tiny` / `base` / `small` / `medium`                                     |
| `stt.compute_type`                 | `int8` (CPU rápido), `int8_float16` (GPU), `float16`, `float32`          |
| `tts.engine`                       | `"auto"` (Piper → pyttsx3), `"piper"` ou `"pyttsx3"`                     |
| `tts.piper_model`                  | Caminho do `.onnx` Piper. `null` = busca em `voices/` do app             |
| `tts.voice_substrings`             | Lista ordenada de substrings para escolher voz pyttsx3 (ex: `["daniel"]`)|
| `actions.programs`                 | Mapa `nome -> caminho.exe` (suporta `%APPDATA%`, `%USERPROFILE%`)        |
| `actions.default_folder`           | Pasta padrão para criar/mover/deletar arquivos                           |
| `actions.allow_shutdown`           | Permitir desligar/reiniciar via voz                                      |
| `intents.use_llm_fallback`         | Habilitar fallback Ollama para frases não reconhecidas                   |
| `wake_word.enabled`                | (Reservado) wake word futuro                                             |

---

## Comandos suportados (exemplos)

| Você diz                             | Ação                                                |
| ------------------------------------ | --------------------------------------------------- |
| “abrir chrome”                       | Abre o Chrome (via `actions.programs.chrome`)      |
| “abrir bloco de notas”               | Abre o Notepad                                      |
| “fechar chrome”                      | `taskkill /IM chrome.exe /F`                        |
| “criar pasta chamada projetos”       | Cria `default_folder/projetos`                      |
| “criar arquivo chamado notas.txt”    | Cria `default_folder/notas.txt`                     |
| “deletar pasta projetos”             | Remove a pasta                                      |
| “mover notas.txt para arquivos”      | Move dentro de `default_folder`                     |
| “pesquisar gatos no google”          | Abre busca no navegador padrão                      |
| “digitar olá mundo”                  | Digita texto na janela em foco (pyautogui)          |
| “aumentar volume” / “diminuir volume”| Pressiona teclas de volume                          |
| “que horas são”                      | Fala a hora atual                                   |
| “que dia é hoje”                     | Fala a data atual                                   |
| “desligar computador”                | `shutdown /s /t 30` (cancelável)                    |
| “cancelar desligamento”              | `shutdown /a`                                       |
| “reiniciar computador”               | `shutdown /r /t 30`                                 |
| “pausar escuta”                      | Para de processar áudio até retomar                 |
| “sair do assistente”                 | Encerra o app                                       |
| “bom dia” / “oi”                     | Resposta simpática                                  |

A arquitetura permite adicionar novas regras em
[`modules/intent_parser.py`](modules/intent_parser.py) (função `_build_rules`)
e o handler correspondente em
[`modules/action_executor.py`](modules/action_executor.py).

---

## Roadmap (preparado, não implementado)

- **Wake word** (“Jarvis”) — esqueleto em `config.wake_word`. Sugerido:
  [`openwakeword`](https://github.com/dscripka/openWakeWord) ou Porcupine.
- **LLM local** — `intents.use_llm_fallback = true` ativa um endpoint compatível
  com Ollama (`/api/generate`) para classificar frases livres.
- **Memória** — adicionar um `modules/memory.py` que persiste fatos/histórico
  em SQLite local.
- **Automações complexas** — encadear ações (macros) e parametrizá-las.

---

## Logs

- Windows: `%LOCALAPPDATA%\VozAssistente\logs\assistant.log`
- Linux/macOS (dev): `~/.voz-assistente/logs/assistant.log`

Rotação automática (1 MB × 3 backups).

---

## Solução de problemas

- **“Microfone indisponível”** — confira em *Configurações → Privacidade →
  Microfone* se os apps desktop podem usar o mic. Ajuste `audio.device_index`
  com o valor de `--list-devices`.
- **Demora no primeiro comando** — o modelo Whisper é baixado e carregado
  preguiçosamente. O carregamento ocorre em background (warmup) ao iniciar.
- **TTS pula palavras** — aumente `tts.rate` (mais devagar) e verifique se a
  voz pt-BR está instalada no Windows (Configurações → Hora e idioma → Voz).
- **STT entende inglês** — confirme `general.language: "pt"` e
  `stt.model_size: "small"` ou maior. `tiny` tem qualidade limitada em pt-BR.

---

## Licença

MIT.
