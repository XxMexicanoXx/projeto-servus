@echo off
REM ============================================================================
REM Build completo do VozAssistente:
REM   1) build.bat (PyInstaller -> dist\VozAssistente.exe)
REM   2) Inno Setup (installer_output\VozAssistente-Setup-1.0.0.exe)
REM
REM Pre-requisitos:
REM   - Python 3.10+
REM   - Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
REM     -> instale em C:\Program Files (x86)\Inno Setup 6 (default).
REM ============================================================================

setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION

echo === [1/2] Empacotando o .exe (PyInstaller) ===
call build.bat
if errorlevel 1 (
    echo Falha no build.bat.
    exit /b 1
)

echo.
echo === [2/2] Compilando o instalador (Inno Setup) ===

set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "!ISCC!" (
    set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
)
if not exist "!ISCC!" (
    where ISCC.exe >nul 2>nul
    if not errorlevel 1 (
        for /f "delims=" %%I in ('where ISCC.exe') do set "ISCC=%%I"
    )
)
if not exist "!ISCC!" (
    echo.
    echo ERRO: Inno Setup 6 nao encontrado.
    echo   Instale em https://jrsoftware.org/isinfo.php
    echo   e tente novamente, ou rode manualmente:
    echo     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
    exit /b 2
)

if not exist installer_output mkdir installer_output

"!ISCC!" /Qp installer.iss
if errorlevel 1 (
    echo Falha na compilacao do instalador.
    exit /b 1
)

echo.
echo ============================================================
echo  Instalador gerado:
for %%F in (installer_output\VozAssistente-Setup-*.exe) do echo     %%~fF
echo ============================================================
endlocal
