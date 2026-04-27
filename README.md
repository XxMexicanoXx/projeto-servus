# VozAssistente

Assistente pessoal por voz **100% local** para Windows, em português brasileiro.
Roda em segundo plano, escuta comandos pelo microfone, interpreta intents,
executa ações no PC e responde por voz.

> **Status:** versão 1.0 — base funcional pronta. Estrutura preparada para
> evoluir com wake word, LLM local (Ollama) e automações mais complexas.

---

## Recursos

- **STT offline** com [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) (modelo configurável: `tiny`/`base`/`small`/`medium`)
- **TTS offline** via `pyttsx3` (SAPI5 no Windows, escolhe voz pt-BR automaticamente)
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
| `tts.voice_substring`              | Substring para escolher voz (ex: `"portuguese"`, `"maria"`, `"daniel"`) |
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
