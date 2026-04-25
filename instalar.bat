@echo off
cd /d "%~dp0"
echo ========================================
echo  Instalando Keilinks...
echo ========================================

:: Cria ambiente virtual
python -m venv .venv
call .venv\Scripts\activate

:: Atualiza pip
python -m pip install --upgrade pip

:: Instala PyTorch com CUDA 12.4 (driver detectado: 12.4)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

:: Instala dependências
pip install -r requirements.txt

:: keyboard precisa de permissão de admin no Windows pra funcionar em background
:: Se der erro ao usar atalhos, rode o iniciar.bat como Administrador

echo.
echo ========================================
echo  Instalacao concluida!
echo  Execute: iniciar.bat
echo ========================================
pause
