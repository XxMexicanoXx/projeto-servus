# Guia de Teste — VozAssistente

> Esse guia assume **Windows 10/11** com PowerShell. Tempo total: **15–25 min**
> (a maior parte é o download do modelo Whisper na primeira execução).

---

## 0. Pré-requisitos

Verifique se você já tem (ou instale agora):

| Item                 | Como verificar                              | Onde baixar                                                             |
| -------------------- | ------------------------------------------- | ----------------------------------------------------------------------- |
| **Python 3.10–3.12** | `python --version` (recomendo 3.11)         | https://www.python.org/downloads/windows/ — marque **"Add to PATH"**    |
| **Git**              | `git --version`                             | https://git-scm.com/download/win                                        |
| **Microfone ativo**  | Configurações → Privacidade → Microfone     | Permita "Apps de desktop" usarem o mic                                  |
| **Voz pt-BR no SAPI**| Configurações → Hora e Idioma → Voz         | Adicione a voz **Maria** ou **Daniel** (pt-BR) — opcional mas recomendado |

> Se faltar alguma coisa, instale e reabra o PowerShell antes de continuar.

---

## 1. Clonar o repositório e ir para a branch do PR

Abra o **PowerShell** (não precisa ser admin) numa pasta que você queira:

```powershell
git clone https://github.com/XxMexicanoXx/projeto-servus.git
cd projeto-servus
git checkout devin/1777300723-initial-implementation
```

Confira que os arquivos estão lá:

```powershell
dir
# Deve mostrar: assistant, modules, utils, requirements.txt, build.bat, README.md, etc.
```

---

## 2. Criar ambiente virtual e instalar dependências

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> Se der erro **"execution of scripts is disabled"**, rode uma vez:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` e responda **S**.

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Esse passo demora **~3 a 5 min** porque baixa `faster-whisper`, `torch` (não), `numpy`, `pyttsx3`, `pystray`, `Pillow`, `sounddevice`, `pyautogui`, `pyinstaller` e dependências.

> Se aparecer erro de compilação em `pyaudio`, ignore — não usamos esse pacote;
> usamos `sounddevice`. Se for `sounddevice` que falhar, instale o
> [Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe).

Confirme que tudo subiu:

```powershell
python -c "import sounddevice, pyttsx3, pystray, faster_whisper, numpy; print('OK')"
```

Deve imprimir `OK`.

---

## 3. Descobrir o índice do microfone

```powershell
python -m assistant.main --list-devices
```

Saída de exemplo:

```
{'index': 0, 'name': 'Microphone (Realtek Audio)', 'channels': 2, 'default_sample_rate': 48000.0}
{'index': 2, 'name': 'Headset (Bluetooth)',         'channels': 1, 'default_sample_rate': 16000.0}
```

**Anote o índice do mic que você quer usar.**

---

## 4. Ajustar `config.json`

Abra `assistant\config.json` no editor (Notepad serve):

```powershell
notepad assistant\config.json
```

Edite estes campos com base no seu PC:

```jsonc
{
  "audio": {
    "device_index": 0,                  // <- coloque o índice do passo 3 (ou null para o padrão)
    "silence_threshold_rms": 0.012      // <- aumente para 0.03–0.05 se houver ruído de fundo
  },
  "actions": {
    "programs": {
      "chrome":          "C:/Program Files/Google/Chrome/Application/chrome.exe",
      "spotify":         "%APPDATA%/Spotify/Spotify.exe"
      // adicione/edite o que quiser
    },
    "default_folder":   "%USERPROFILE%/Documents/Assistente",
    "shutdown_delay_seconds": 30,        // janela para dizer "cancelar desligamento"
    "allow_shutdown": true               // mude para false se quiser desativar
  }
}
```

Salve.

> O caminho do Chrome às vezes está em
> `C:\Program Files (x86)\Google\Chrome\Application\chrome.exe` em
> instalações antigas. Confira clicando com botão direito no atalho do Chrome
> → **Local do arquivo**.

---

## 5. Primeira execução em modo dev

```powershell
python -m assistant.main
```

O que esperar:

1. Logs no terminal mostrando:
   - `Microfone aberto (rate=16000, ...)`
   - `Carregando faster-whisper modelo=small device=cpu compute=int8 ...`
     → **na primeira vez**, baixa **~244 MB** do modelo (pode levar 1–3 min).
   - `Modelo carregado em XX.Xs.`
   - `TTS pyttsx3 pronto (...)` e `Voz TTS selecionada: Microsoft Maria - Portuguese...`
2. O assistente fala: **"Assistente pronto."**
3. **Ícone aparece na bandeja do sistema** (canto inferior direito, perto do relógio). Pode estar em "ícones ocultos" — clique na seta ↑.

Caso a voz não saia: verifique o volume do sistema, e que tem voz pt-BR
instalada (Configurações → Hora e Idioma → Voz → Adicionar voz → Português (Brasil)).

---

## 6. Teste de comandos por voz (modo dev)

Fale **claramente**, sem pressa, e espere ~1 segundo após terminar a frase.

Comece com os comandos seguros (não destrutivos):

| 🗣️ Diga                                | ✅ Resposta esperada (voz)              | 🔍 Verifique também                              |
| --------------------------------------- | ----------------------------------------- | ------------------------------------------------ |
| "que horas são"                         | "Agora são X horas e Y minutos."          | Hora bate com o relógio                          |
| "que dia é hoje"                        | "Hoje é DD de MÊS de AAAA."               | Data bate                                        |
| "olá"                                   | "Olá! Como posso ajudar?"                 | —                                                |
| "abrir bloco de notas"                  | "Abrindo bloco de notas."                 | Notepad abriu                                    |
| "abrir calculadora"                     | "Abrindo calculadora."                    | Calculadora abriu                                |
| "criar pasta chamada teste"             | "Pasta teste criada em ..."               | `Documents\Assistente\teste\` existe             |
| "criar arquivo chamado nota.txt"        | "Arquivo nota.txt criado em ..."          | `Documents\Assistente\nota.txt` existe           |
| "deletar pasta teste"                   | "Pasta teste deletada."                   | Pasta sumiu                                      |
| "apagar arquivo nota.txt"               | "Arquivo nota.txt deletado."              | Arquivo sumiu                                    |
| "pesquisar gatos no google"             | "Pesquisando por gatos no google."        | Aba do navegador abre com a busca                |
| "abrir chrome" (se config OK)           | "Abrindo chrome."                         | Chrome abre                                      |
| "fechar chrome"                         | "Fechando chrome."                        | Chrome fecha                                     |
| "aumentar volume" / "diminuir volume"   | "Volume ajustado."                        | Volume do sistema sobe/desce 5 níveis            |
| "pausar escuta"                         | "Escuta pausada."                         | Tray vira "parado"; comandos param de funcionar  |
| **clique direito no tray → Iniciar escuta** | "Escuta retomada."                    | Volta a responder                                |

### Comandos destrutivos (faça por último, com calma)

| 🗣️ Diga                  | ✅ Resposta                                                                   |
| ------------------------- | ------------------------------------------------------------------------------ |
| "desligar computador"     | "Desligando em 30 segundos. Diga 'cancelar desligamento' para abortar."        |
| "cancelar desligamento"   | "Desligamento cancelado."                                                      |

> Se quiser desativar isso, ponha `"allow_shutdown": false` no config.

### Encerrando

Diga **"sair do assistente"** ou clique direito no tray → **Sair**. O app fecha
normalmente.

---

## 7. Conferir os logs

Abra:

```
%LOCALAPPDATA%\VozAssistente\logs\assistant.log
```

(no Explorer, cole o caminho na barra de endereço.)

Procure por:

- `Microfone aberto` — captura ok
- `STT (X.XXs detectados): 'transcrição'` — STT entendeu
- `Intent <nome> -> 'resposta'` — intent classificado
- Erros (`ERROR`/`WARNING`) — me mande se houver

---

## 8. Build do `.exe`

Com a venv ativa ainda:

```powershell
.\build.bat
```

O script faz:
1. Cria `.venv` se não existir (já temos)
2. Instala/atualiza requirements
3. Limpa `build/` e `dist/`
4. Roda `pyinstaller assistant.spec`
5. Copia `assistant\config.json` para `dist\config.json`

Demora **3–8 min** dependendo do PC. Saída final:

```
dist\
  ├── VozAssistente.exe   (~150–250 MB)
  └── config.json
```

### Testando o `.exe`

```powershell
cd dist
.\VozAssistente.exe
```

- **Não** abre janela de console (é app GUI).
- Aparece o **ícone na bandeja**.
- Diga "que horas são" — fala a hora.
- Para sair: tray → Sair (ou diga "sair do assistente").

> O primeiro launch do `.exe` é mais lento (extrai libs internas para `%TEMP%`).
> Subsequentes ficam ~2 s mais rápidos.

### Movendo para outra pasta

Para confirmar que está realmente standalone:

```powershell
mkdir C:\VozAssistente
copy dist\VozAssistente.exe C:\VozAssistente\
copy dist\config.json       C:\VozAssistente\
cd C:\VozAssistente
.\VozAssistente.exe
```

Edite `C:\VozAssistente\config.json` para personalizar — o `.exe` lê
**sempre** o `config.json` ao lado dele.

> 💡 Para iniciar com o Windows: crie um atalho de `VozAssistente.exe` em
> `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`.
> Ou — melhor — use o **instalador** descrito no passo 9.

---

## 9. Gerar o pacote de instalação (`Setup.exe`)

Depois que o `dist\VozAssistente.exe` está funcionando, gere o instalador
padrão Windows:

### 9.1 Instalar o Inno Setup (uma vez)

Baixe e instale o **Inno Setup 6**:
https://jrsoftware.org/isdl.php (clique em **"innosetup-6.x.x.exe"**)

Aceite todos os defaults — instala em `C:\Program Files (x86)\Inno Setup 6`.

### 9.2 Compilar o instalador

Na raiz do repo, com a `.venv` ativa:

```cmd
.\build_installer.bat
```

O script:
1. Roda `build.bat` (PyInstaller → `dist\VozAssistente.exe`)
2. Localiza o `ISCC.exe` automaticamente
3. Compila `installer.iss`
4. Gera `installer_output\VozAssistente-Setup-1.0.0.exe`

Tempo: **5–10 min** (a maior parte é PyInstaller).

### 9.3 Testar o instalador

Dê duplo-clique em `installer_output\VozAssistente-Setup-1.0.0.exe`.

Wizard padrão Windows:
1. Idioma → **Português (Brasil)**
2. Pasta de instalação (default `C:\Program Files\VozAssistente`)
3. **Tasks** — marque o que quiser:
   - [ ] Criar atalho na Área de Trabalho
   - [ ] Iniciar o VozAssistente junto com o Windows
4. Instalar → **Concluir** (pode marcar "Executar VozAssistente agora")

Confirme:

| Item                                                              | Onde verificar                                                    |
| ----------------------------------------------------------------- | ----------------------------------------------------------------- |
| Atalho no Menu Iniciar                                            | Menu Iniciar → digite "Voz"                                       |
| Atalho "Editar configuração" abre o config.json                   | Menu Iniciar → "VozAssistente (Editar configuração)"              |
| `config.json` está em `%APPDATA%\VozAssistente\`                  | Win+R → `%APPDATA%\VozAssistente`                                 |
| Pasta de instalação correta                                       | Win+R → `C:\Program Files\VozAssistente`                          |
| App roda sem precisar de venv ou Python                           | Duplo-clique no atalho                                            |
| (Se marcou autostart) O app abre ao logar no Windows              | Reiniciar e ver o ícone no tray                                   |
| **Desinstalador funciona**                                        | Configurações → Apps → VozAssistente → Desinstalar                |

Após desinstalar, confirme:
- `C:\Program Files\VozAssistente\` é apagada
- Atalhos somem
- `%APPDATA%\VozAssistente\config.json` **continua lá** (preserva sua config
  para reinstalações futuras — apague manualmente se quiser limpar de vez)

---

## 10. O que reportar de volta

Se tudo funcionou, é só me dizer **"funcionou"** e fechamos o PR via merge.

Se algo deu errado, me mande:

1. **Em qual passo (1–8) parou.**
2. **Mensagem de erro completa** (cole no chat).
3. **Conteúdo do log** (`%LOCALAPPDATA%\VozAssistente\logs\assistant.log`)
   se for problema em runtime.
4. **Versão do Python** (`python --version`) e do Windows.

Eu corrijo direto na branch.

---

## Problemas comuns

| Sintoma                                                              | Causa provável                          | Correção                                                                                              |
| -------------------------------------------------------------------- | --------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `ModuleNotFoundError: No module named 'sounddevice'`                 | Venv não ativada                        | `.\.venv\Scripts\Activate.ps1` antes de rodar                                                         |
| Não captura áudio nenhum                                             | `device_index` errado                   | Rode `--list-devices` e ajuste                                                                        |
| Captura ruído contínuo                                               | `silence_threshold_rms` muito baixo     | Aumente para `0.03` ou `0.05` no config                                                               |
| STT entende inglês                                                   | Modelo `tiny` ou `language` errado      | `"model_size": "small"` e `"language": "pt"`                                                          |
| TTS sem voz / robótico                                               | Não tem voz pt-BR no Windows            | Configurações → Hora/Idioma → Voz → Adicionar voz → Português (Brasil)                                |
| `pystray` não mostra tray                                            | Falta da Pillow ou política do Windows  | Confirme `pip install Pillow pystray` ok; reinicie o Explorer (Ctrl+Shift+Esc → Reiniciar Explorer)   |
| `.exe` muito grande (300+ MB)                                        | Whisper `medium` empacotado             | Use `model_size: "base"` ou `"tiny"` no config                                                        |
| `.exe` falha a abrir com erro `Failed to load Python DLL`            | Python diferente da venv                | Recriar venv e rodar `build.bat` de novo                                                              |
| Antivírus reclama do `.exe`                                          | Comum em PyInstaller onefile            | Adicione exceção; ou assine o exe digitalmente para distribuir                                         |
