#!/bin/sh

echo "Iniciando o Rastreador de Ônibus RJ (Modo Nativo Supervisor)..."
echo "Aguardando estabilização do sistema..."
sleep 2

exec python3 onibus.py
