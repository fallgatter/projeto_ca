@echo off
setlocal
pushd "%~dp0" || exit /b 1

set "python_cmd="
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1 && set "python_cmd=.venv\Scripts\python.exe"
)
if not defined python_cmd (
    py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1 && set "python_cmd=py -3"
)
if not defined python_cmd (
    python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1 && set "python_cmd=python"
)
if not defined python_cmd (
    echo Python 3.10 ou superior nao encontrado.
    pause
    popd
    exit /b 1
)

set "painel_url=http://127.0.0.1:8077"
echo Abrindo o painel em %painel_url%
echo Pressione Ctrl+C nesta janela para encerrar o servidor.

rem Aguarda a pagina do painel antes de abrir o navegador.
start "" /b powershell.exe -NoLogo -NoProfile -NonInteractive -Command ^
    "$url = '%painel_url%'; for ($i = 0; $i -lt 40; $i++) { try { $page = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 1 -ErrorAction Stop; if ($page.Content.Contains('before-map')) { Start-Process -FilePath $url; break } } catch { }; Start-Sleep -Milliseconds 250 }"

%python_cmd% -m onda_verde_senoidal.server --port 8077
set "server_exit=%errorlevel%"
if not "%server_exit%"=="0" (
    echo O servidor do painel foi encerrado com erro.
    pause
)
popd
exit /b %server_exit%
