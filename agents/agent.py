"""
agents/agent.py

Modulo di simulazione agent/producer: invia eventi (metriche o warning) al Control Plane (CP).
Testa il ciclo: generazione evento → invio a CP → decisione/escalation/log.

Autore: MK023 + Copilot
"""

import random
import time
from cp_core.controller import CPController

# --- COLORI (Colorama) ---
from colorama import Fore, Style, init
init(autoreset=True)

def colorize_status(status):
    if status == "ok":
        return Fore.GREEN + Style.BRIGHT + "[OK]" + Style.RESET_ALL
    elif status == "warning":
        return Fore.YELLOW + Style.BRIGHT + "[WARNING]" + Style.RESET_ALL
    elif status == "critical":
        return Fore.RED + Style.BRIGHT + "[CRITICAL]" + Style.RESET_ALL
    else:
        return "[UNKNOWN]"

class Agent:
    """
    Classe base agent: ogni agent rappresenta una risorsa monitorata.
    Può essere estesa per logiche di monitoraggio reali.
    """
    def __init__(self, name, source_type, cp_controller, check_interval=1):
        self.name = name
        self.source_type = source_type
        self.cp_controller = cp_controller
        self.check_interval = check_interval

    def make_event(self):
        """
        Simula la generazione di un evento di stato.
        Sovrascrivibile per logiche reali.
        """
        stato = random.choices(
            ["ok", "warning", "critical"],
            weights=[0.7, 0.2, 0.1],
            k=1
        )[0]
        return {
            "source": self.source_type,
            "status": stato,
            "info": f"Evento simulato da {self.name}"
        }

    def monitor(self, n_events=5):
        """
        Ciclo di monitoraggio: genera e invia n eventi al CP.
        """
        print(Style.BRIGHT + Fore.CYAN + f"[{self.name}] Avvio monitoraggio...\n" + Style.RESET_ALL)
        for i in range(n_events):
            event = self.make_event()
            action = self.cp_controller.receive_event(event)
            status_colored = colorize_status(event["status"])
            print(f"[{self.name}] Evento {i+1}: {status_colored} {event} -> {Fore.MAGENTA}Azione CP:{Style.RESET_ALL} {action}")
            time.sleep(self.check_interval)
        print(Style.BRIGHT + Fore.CYAN + f"\n[{self.name}] Monitoraggio terminato. Controlla 'logs/cp.log'." + Style.RESET_ALL)

# --- AGENT SPECIALIZZATI (puoi aggiungerne quanti vuoi) ---
class MongoDBAgent(Agent):
    def __init__(self, cp_controller, check_interval=1):
        super().__init__("MongoDBAgent", "mongodb", cp_controller, check_interval)

class NASAgent(Agent):
    def __init__(self, cp_controller, check_interval=1):
        super().__init__("NASAgent", "nas", cp_controller, check_interval)

class RabbitMQAgent(Agent):
    def __init__(self, cp_controller, check_interval=1):
        super().__init__("RabbitMQAgent", "rabbitmq", cp_controller, check_interval)

# --- MAIN DI TEST ---
if __name__ == "__main__":
    cp = CPController()
    n_events = 5

    # Scegli quale agent testare (o crea un ciclo per tutti)
    agent_list = [
        MongoDBAgent(cp),
        NASAgent(cp),
        RabbitMQAgent(cp)
    ]
    # Per demo fai girare tutti gli agent uno dopo l'altro
    for agent in agent_list:
        agent.monitor(n_events=n_events)