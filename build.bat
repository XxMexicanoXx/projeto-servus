@echo off
REM ============================================================================
REM Build do VozAssistente.exe (Windows)
REM ----------------------------------------------------------------------------
REM Pre-requisitos:
REM   - Python 3.10+ (recomendado 3.11) instalado e no PATH
REM   - Visual C++ Redistributable (já vem em quase todo Windows moderno)
REM
REM Uso:
REM   build.bat
REM
REM Saida:
REM   dist\VozAssistente.exe
REM ============================================================================

setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION

echo [1/5] Verificando Python...
where python >nul 2>nul
if errorlevel 1 (
    echo Python nao encontrado no PATH. Instale Python 3.10+ e tente novamente.
    exit /b 1
)

echo [2/5] Criando ambiente virtual em .venv...
if not exist .venv (
    python -m venv .venv
    if errorlevel 1 (
        echo Falha ao criar venv.
        exit /b 1
    )
)
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo Falha ao ativar venv.
    exit /b 1
)

echo [3/5] Atualizando pip e instalando dependencias...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Falha instalando dependencias.
    exit /b 1
)

echo [4/5] Limpando builds anteriores...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

echo [5/5] Empacotando com PyInstaller...
pyinstaller assistant.spec --clean --noconfirm
if errorlevel 1 (
    echo Build falhou.
    exit /b 1
)

REM Copia o config.json para o lado do exe (assim o usuario pode editar)
copy /y assistant\config.json dist\config.json >nul

echo.
echo ============================================================
echo  Build concluido: dist\VozAssistente.exe
echo  Edite dist\config.json para personalizar caminhos/comandos.
echo ============================================================
endlocal
