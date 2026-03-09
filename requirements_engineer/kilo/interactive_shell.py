"""
Interaktive Shell für User Kilo Agent

Diese interaktive Shell ermöglicht es Benutzern, Tasks an den User Kilo Agent zu senden.
Sie unterstützt strukturierte Ausgabe und verschiedene Befehle.
"""

import asyncio
import sys
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
import json
import re

# Kodierung auf UTF-8 setzen für Windows-Kompatibilität
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')


class InteractiveShell:
    """
    Interaktive Shell für User Kilo Agent.
    
    Ermöglicht es Benutzern, Tasks an den User Kilo Agent zu senden.
    Unterstützt strukturierte Ausgabe und verschiedene Befehle.
    """
    
    def __init__(self, workspace_dir: Optional[Path] = None):
        """
        Initialisiert die interaktive Shell.
        
        Args:
            workspace_dir: Arbeitsverzeichnis für Dateien (optional)
        """
        self.workspace_dir = Path(workspace_dir) if workspace_dir else Path.cwd()
        self.tasks: List[Dict[str, Any]] = []
        self.current_task_index = 0
        self.running = True
        
    def add_task(self, task: str, priority: int = 0, structured_output: bool = False) -> None:
        """
        Fügt eine Aufgabe zur Liste hinzu.
        
        Args:
            task: Die Aufgabe, die ausgeführt werden soll
            priority: Priorität der Aufgabe (0 = niedrig, 1 = mittel, 2 = hoch)
            structured_output: Ob die Ausgabe strukturiert als JSON zurückgegeben werden soll
        
        Returns:
            Task-Index
        """
        task_index = len(self.tasks)
        self.tasks.append({
            "index": task_index,
            "task": task,
            "priority": priority,
            "structured_output": structured_output,
            "status": "pending",
            "result": None
        })
        return task_index
    
    def get_next_task(self) -> Optional[Dict[str, Any]]:
        """
        Gibt die nächste Aufgabe zurück.
        
        Returns:
            Die nächste Aufgabe oder None, wenn keine Aufgaben mehr vorhanden sind
        """
        pending_tasks = [t for t in self.tasks if t["status"] == "pending"]
        if not pending_tasks:
            return None
        
        # Sortiere nach Priorität (höchste zuerst)
        pending_tasks.sort(key=lambda x: x["priority"], reverse=True)
        return pending_tasks[0]
    
    def update_task_result(self, task_index: int, result: Dict[str, Any]) -> None:
        """
        Aktualisiert das Ergebnis einer Aufgabe.
        
        Args:
            task_index: Index der Aufgabe
            result: Das Ergebnis der Aufgabe
        """
        if task_index < len(self.tasks):
            self.tasks[task_index]["result"] = result
            self.tasks[task_index]["status"] = "completed"
    
    def get_task_status(self) -> Dict[str, Any]:
        """
        Gibt den Status aller Aufgaben zurück.
        
        Returns:
            Dictionary mit Statistiken
        """
        total = len(self.tasks)
        pending = len([t for t in self.tasks if t["status"] == "pending"])
        completed = len([t for t in self.tasks if t["status"] == "completed"])
        failed = len([t for t in self.tasks if t["status"] == "failed"])
        
        return {
            "total": total,
            "pending": pending,
            "completed": completed,
            "failed": failed
        }
    
    def print_status(self):
        """Gibt den Status der Shell aus."""
        status = self.get_task_status()
        
        print(f"\033[95m{'='*60}\033[0m")
        print(f"\033[94m📊 Shell-Status\033[0m")
        print(f"\033[95m{'='*60}\033[0m")
        print(f"\033[92mGesamt: \033[96m{status['total']}\033[0m")
        print(f"\033[93mAusstehend: \033[96m{status['pending']}\033[0m")
        print(f"\033[92mAbgeschlossen: \033[96m{status['completed']}\033[0m")
        print(f"\033[91mFehlgeschlagen: \033[96m{status['failed']}\033[0m")
        print(f"\033[95m{'='*60}\033[0m")
        
        # Zeige Aufgaben an
        if self.tasks:
            print(f"\033[94m📋 Aufgaben:\033[0m")
            for task in self.tasks:
                status_icon = "⏳" if task["status"] == "pending" else "✓" if task["status"] == "completed" else "✗" if task["status"] == "failed" else "❓"
                priority_color = "\033[93m" if task["priority"] == 0 else "\033[96m" if task["priority"] == 1 else "\033[95m" if task["priority"] == 2 else ""
                
                print(f"  {status_icon} \033[94m[{task['index']:2d}]\033[0m \033[96m{task['task']}\033[0m")
        
        print(f"\033[95m{'='*60}\033[0m")
    
    def print_task_result(self, task_index: int):
        """Gibt das Ergebnis einer Aufgabe aus."""
        if task_index < len(self.tasks):
            task = self.tasks[task_index]
            result = task.get("result", {})
            
            print(f"\n\033[95m{'='*60}\033[0m")
            print(f"\033[94m📋 Ergebnis für Aufgabe {task['index']}: {task['task']}\033[0m")
            print(f"\033[95m{'='*60}\033[0m")
            
            if result.get("success", False):
                print(f"\033[91m✗ Fehler:\033[0m \033[93m{result.get('error', 'Unbekannter Fehler')}\033[0m")
            elif result.get("structured", False):
                # Unstrukturierte Ausgabe
                stdout = result.get("stdout", "")
                stderr = result.get("stderr", "")
                
                if stdout:
                    print(f"\033[92m✓ Ausgabe:\033[0m")
                    print(f"\033[96m{stdout}\033[0m")
                if stderr:
                    print(f"\033[91m✗ Fehler:\033[0m")
                    print(f"\033[93m{stderr}\033[0m")
            else:
                # Strukturierte Ausgabe
                stdout = result.get("stdout", "")
                stderr = result.get("stderr", "")
                
                # Versuche, JSON zu extrahieren
                response_text = stdout + stderr
                json_match = re.search(r'\{[^{}]*"stdout"[^{}]*"stderr"[^{}]*\}', response_text, re.DOTALL)
                if json_match:
                    try:
                        result_json = json.loads(json_match.group())
                        # Extrahiere stdout oder stderr
                        if 'stdout' in result_json and result_json['stdout']:
                            clean_stdout = result_json['stdout'].replace('\\n', '\n').replace('\\r', '\r').strip()
                            if clean_stdout:
                                print(f"\033[92m✓ stdout:\033[0m")
                                print(f"\033[96m{clean_stdout}\033[0m")
                        elif 'stderr' in result_json and result_json['stderr']:
                            clean_stderr = result_json['stderr'].replace('\\n', '\n').replace('\\r', '\r').strip()
                            if clean_stderr:
                                print(f"\033[91m✗ stderr:\033[0m")
                                print(f"\033[93m{clean_stderr}\033[0m")
                    except:
                        pass
                
                if not stdout and not stderr:
                    print(f"\033[93m⚠ Keine Ausgabe erhalten\033[0m")
            
            print(f"\033[95m{'='*60}\033[0m")
    
    def stop(self):
        """Stoppt die interaktive Shell."""
        self.running = False
        print("\n\033[92m🛑 Shell gestoppt\033[0m")
    
    def save_tasks(self, filename: Optional[str] = None) -> None:
        """
        Speichert alle Aufgaben in einer JSON-Datei.
        
        Args:
            filename: Dateiname (optional)
        
        Returns:
            Pfad zur gespeicherten Datei oder None
        """
        if not self.tasks:
            print("\033[93m⚠ Keine Aufgaben zum Speichern\033[0m")
            return None
        
        if filename is None:
            timestamp = asyncio.get_event_loop().time()
            filename = f"shell_tasks_{int(timestamp)}.json"
        
        filepath = self.workspace_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.tasks, f, indent=2, ensure_ascii=False)
        
        print(f"\033[92m💾 Aufgaben gespeichert:\033[0m \033[96m{filepath}\033[0m")
        return filepath
    
    def load_tasks(self, filename: str) -> List[Dict[str, Any]]:
        """
        Lädt Aufgaben aus einer JSON-Datei.
        
        Args:
            filename: Dateiname
        
        Returns:
            Liste der Aufgaben
        """
        filepath = self.workspace_dir / filename
        
        if not filepath.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            tasks = json.load(f)
        
        self.tasks = tasks
        print(f"\033[92m✓ Aufgaben geladen:\033[0m \033[96m{filepath}\033[0m")
        return tasks


async def run_interactive_shell(
    workspace_dir: Optional[str] = None,
    tasks_file: Optional[str] = None
):
    """
    Startet die interaktive Shell.
    
    Args:
        workspace_dir: Arbeitsverzeichnis für Dateien (optional)
        tasks_file: Pfad zur Aufgaben-Datei (optional)
    """
    shell = InteractiveShell(workspace_dir=workspace_dir)
    
    # Aufgaben aus Datei laden, falls angegeben
    if tasks_file:
        try:
            shell.load_tasks(tasks_file)
            print(f"\033[92m✓ Aufgaben aus Datei geladen:\033[0m \033[96m{tasks_file}\033[0m")
        except FileNotFoundError:
            print(f"\033[93m⚠ Datei nicht gefunden: {tasks_file}\033[0m")
    
    print(f"\033[95m{'='*60}\033[0m")
    print(f"\033[96m🤖 Interaktive Shell für User Kilo Agent\033[0m")
    print(f"\033[95m{'='*60}\033[0m")
    print(f"\033[94mVerfügbare Befehle:\033[0m")
    print(f"  \033[96madd <task> [priority] [structured]\033[0m")
    print(f"  \033[96mstatus\033[0m")
    print(f"  \033[96mnext\033[0m")
    print(f"  \033[96mresult <index>\033[0m")
    print(f"  \033[96mstop\033[0m")
    print(f"  \033[96msave <filename>\033[0m")
    print(f"  \033[96mload <filename>\033[0m")
    print(f"  \033[96mexit\033[0m")
    print(f"\033[95m{'='*60}\033[0m")
    
    # Hauptschleife
    while shell.running:
        try:
            # Benutzereingabe
            user_input = input("\033[94mShell>\033[0m ").strip()
            
            if not user_input:
                continue
            
            # Befehle parsen
            if user_input.startswith("add "):
                # add <task> [priority] [structured]
                parts = user_input[4:].strip().split()
                if len(parts) >= 1:
                    task = parts[0].strip()
                    priority = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                    structured = len(parts) > 2 and parts[2].lower() == "true"
                    
                    task_index = shell.add_task(task, priority, structured)
                    print(f"\033[92m✓ Aufgabe hinzugefügt (Index: {task_index})\033[0m")
            
            elif user_input.startswith("status"):
                shell.print_status()
            
            elif user_input.startswith("next"):
                task = shell.get_next_task()
                if task:
                    print(f"\033[94m📋 Nächste Aufgabe:\033[0m \033[96m{task['task']}\033[0m")
                    print(f"  \033[96mFühre aus...\033[0m")
                    
                    # Hier würde der User Kilo Agent die Aufgabe ausführen
                    # Für jetzt zeigen wir nur die Aufgabe an
                    print(f"  \033[93mHinweis: Diese Aufgabe wird vom User Kilo Agent ausgeführt\033[0m")
            
            elif user_input.startswith("result"):
                # result <index>
                parts = user_input[7:].strip().split()
                if len(parts) >= 1 and parts[0].isdigit():
                    task_index = int(parts[0])
                    shell.print_task_result(task_index)
                else:
                    print("\033[93m⚠ Ungültiges Format. Verwende: result <index>\033[0m")
            
            elif user_input.startswith("save"):
                # save <filename>
                filename = user_input[5:].strip() if len(user_input) > 5 else None
                if filename:
                    shell.save_tasks(filename)
                else:
                    print("\033[93m⚠ Ungültiges Format. Verwende: save <filename>\033[0m")
            
            elif user_input.startswith("load"):
                # load <filename>
                filename = user_input[5:].strip() if len(user_input) > 5 else None
                if filename:
                    shell.load_tasks(filename)
                else:
                    print("\033[93m⚠ Ungültiges Format. Verwende: load <filename>\033[0m")
            
            elif user_input.startswith("stop"):
                shell.stop()
            
            elif user_input.startswith("exit"):
                shell.stop()
                print("\033[92m👋 Auf Wiedersehen!\033[0m")
                break
            
            elif user_input in ["help", "?"]:
                print(f"\033[94m📚 Hilfe:\033[0m")
                print(f"\033[95m{'='*60}\033[0m")
                print(f"\033[94mVerfügbare Befehle:\033[0m")
                print(f"  \033[96madd <task> [priority] [structured]\033[0m")
                print(f"    Fügt eine Aufgabe hinzu (z.B. 'add python --version 0')")
                print(f"    priority: 0=niedrig, 1=mittel, 2=hoch (Standard: 0)")
                print(f"    structured: true/false (Standard: false)")
                print(f"  \033[96mstatus\033[0m")
                print(f"    Zeigt den Status aller Aufgaben an\033[0m")
                print(f"  \033[96mnext\033[0m")
                print(f"    Führt die nächste Aufgabe aus\033[0m")
                print(f"  \033[96mresult <index>\033[0m")
                print(f"    Zeigt das Ergebnis einer Aufgabe an (z.B. 'result 0')\033[0m")
                print(f"  \033[96msave <filename>\033[0m")
                print(f"    Speichert alle Aufgaben in einer JSON-Datei\033[0m")
                print(f"  \033[96mload <filename>\033[0m")
                print(f"    Lädt Aufgaben aus einer JSON-Datei\033[0m")
                print(f"  \033[96mstop\033[0m")
                print(f"    Stoppt die interaktive Shell\033[0m")
                print(f"  \033[96mexit\033[0m")
                print(f"    Beendet die interaktive Shell\033[0m")
                print(f"\033[95m{'='*60}\033[0m")
        
        except KeyboardInterrupt:
            print("\n\033[92m👋 Auf Wiedersehen!\033[0m")
            shell.stop()
        
        except Exception as e:
            print(f"\n\033[91m✗ Fehler: {str(e)}\033[0m")


if __name__ == "__main__":
    import sys
    
    # Prüfe, ob die interaktive Shell direkt aufgerufen wird
    if len(sys.argv) > 1 and sys.argv[1] == "--shell":
        # Interaktive Shell starten
        workspace_dir = sys.argv[2] if len(sys.argv) > 2 else None
        tasks_file = sys.argv[3] if len(sys.argv) > 3 else None
        
        asyncio.run(run_interactive_shell(
            workspace_dir=workspace_dir,
            tasks_file=tasks_file
        ))
    else:
        print("\033[93m⚠ Starte die interaktive Shell mit: python interactive_shell.py --shell\033[0m")
        print("\033[94mVerfügbare Befehle:\033[0m")
        print("  add <task> [priority] [structured]")
        print("  status")
        print("  next")
        print("  result <index>")
        print("  save <filename>")
        print("  load <filename>")
        print("  stop")
        print("  exit")
        print("  help")
