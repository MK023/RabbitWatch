#!/bin/bash
# Script di avvio automatico del producer NAS Monitoring

# Posizionati nella directory dello script
cd /var/services/homes/Marco/nas_metrics_rabbitmq || exit 1

# Crea la cartella logs se non esiste
mkdir -p logs

# Attiva virtualenv se usato (decommenta la riga seguente se usi venv)
# source venv/bin/activate

# Avvia il producer in background, logga stdout e stderr su file nella cartella logs
nohup python3 metrics_producer.py > logs/producer_stdout.log 2> logs/producer_stderr.log &

# (opzionale) Scrivi il PID su file per eventuale stop/script di controllo
echo $! > producer.pid