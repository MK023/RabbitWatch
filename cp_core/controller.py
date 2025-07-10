"""
cp_core/controller.py

Modulo principale per la ricezione e gestione degli eventi dagli agent.
Gestisce escalation su più livelli in caso di recovery fallite consecutive.
Gestione robusta: warning su servizi nuovi, thread-safe, error logging.

Autore: MK023 + Copilot
"""

import os
import threading
from cp_core.recovery import RecoveryManager

class CPController:
    def __init__(self):
        self.recovery_manager = RecoveryManager()
        os.makedirs("logs", exist_ok=True)
        self.failure_counters = {}
        self.known_sources = set(['mongodb', 'nas', 'rabbitmq'])
        self.escalation_thresholds = {
            'mongodb': [1, 3, 5],
            'nas': [1, 2, 4],
            'rabbitmq': [1, 2, 4],
            'default': [1, 3, 5]
        }
        self.lock = threading.Lock()  # Protegge accesso a failure_counters e known_sources

    def receive_event(self, event):
        source = event.get("source").lower()
        status = event.get("status")
        success = None
        recovery_result = None

        # Warning su source non noto
        with self.lock:
            if source not in self.known_sources:
                print(f"[WARNING] Nuovo servizio sconosciuto ricevuto: '{source}'. Uso soglie default.")
                self.known_sources.add(source)

        if status == "ok":
            return "Nessuna azione necessaria."
        if status == "warning":
            self.notify_user(event, recovery=False)
            return "Azione di monitoraggio consigliata. Utente avvisato."
        if status == "critical":
            success, recovery_result = self.recovery_manager.recover(event)
            with self.lock:
                if not success:
                    self.failure_counters[source] = self.failure_counters.get(source, 0) + 1
                else:
                    self.failure_counters[source] = 0
                level = self.get_escalation_level(source)
            self.notify_user(event, recovery=True, detail=recovery_result, success=success, level=level)
            if success:
                return f"Recovery automatica riuscita e utente avvisato. Dettaglio: {recovery_result}"
            else:
                return f"ATTENZIONE: Recovery automatica FALLITA! Livello escalation: {level} - Utente avvisato. Dettaglio: {recovery_result}"
        return "Stato evento non riconosciuto."

    def get_escalation_level(self, source):
        thresholds = self.escalation_thresholds.get(source, self.escalation_thresholds['default'])
        failures = self.failure_counters.get(source, 0)
        for i, soglia in enumerate(thresholds):
            if failures < soglia:
                return i
        return len(thresholds)

    def notify_user(self, event, recovery, detail=None, success=None, level=0):
        source = event.get("source")
        status = event.get("status")
        msg = ""
        if recovery:
            esito = "SUCCESSO" if success else "FALLIMENTO"
            msg = f"NOTIFICA: RECOVERY {esito} su {source} (status: {status}). Dettaglio: {detail}"
            if not success:
                msg += f" | Escalation livello {level}"
                if level == 1:
                    msg += " | Invio alert via email"
                elif level == 2:
                    msg += " | Invio alert Telegram + email"
                elif level >= 3:
                    msg += " | Chiamata operatore umano!"
        else:
            msg = f"NOTIFICA: WARNING da {source} (status: {status})"

        print(f"[NOTIFICA] {msg}")
        try:
            with open("logs/cp.log", "a") as logf:
                logf.write(msg + "\n")
        except Exception as e:
            print(f"[ERROR] Impossibile scrivere su log: {e}")