@echo off
cd /d "%~dp0"
echo Iniciando Keilinks...
:: ─── Otimizações de VRAM para Blackwell (RTX 50xx) ───────────────────────────
:: Flash Attention: reduz VRAM do mecanismo de atenção significativamente
set OLLAMA_FLASH_ATTENTION=1

:: KV Cache quantizado: reduz VRAM do contexto pela metade (q8_0) com impacto mínimo
:: Troca para q4_0 se ainda faltar VRAM (reduz a 1/3, pequena perda de qualidade)
set OLLAMA_KV_CACHE_TYPE=q8_0

:: Garante que o Ollama usa a GPU correta
set CUDA_VISIBLE_DEVICES=0
set PYTHONNOUSERSITE=1

"%~dp0.venv\Scripts\python.exe" main.py
pause
