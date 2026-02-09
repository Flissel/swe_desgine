"""
Kilocode CLI Tool - Python Wrapper für Kilocode CLI

Dieses Tool ermöglicht es einem Agenten, Kilocode CLI-Befehle über die Kommandozeile auszuführen.
Es unterstützt die wichtigsten CLI-Optionen und Befehle.

Verfügbare CLI-Optionen:
    -m, --mode <mode>           Set the mode (architect, code, ask, debug, orchestrator, review)
    -w, --workspace <path>      Path to workspace directory
    -a, --auto                  Run in autonomous mode (non-interactive)
    --yolo                      Auto-approve all tool permissions
    -j, --json                  Output messages as JSON (requires --auto)
    -i, --json-io               Bidirectional JSON mode (no TUI, stdin/stdout enabled)
    -c, --continue              Resume the last conversation
    -t, --timeout <seconds>     Timeout for autonomous mode
    -p, --parallel              Run in parallel mode
    -e, --existing-branch <branch>  Work on existing branch (parallel mode)
    -P, --provider <id>         Select provider by ID
    -M, --model <model>         Override model for selected provider
    -s, --session <sessionId>   Restore a session by ID
    -f, --fork <shareId>        Fork a session by ID
    --nosplash                  Disable welcome message
    --append-system-prompt <text>  Append custom instructions
    --append-system-prompt-file <path>  Read custom instructions from file
    --on-task-completed <prompt>  Send custom prompt on task completion
    --attach <path>              Attach a file (can be repeated)

Verfügbare CLI-Befehle:
    auth                        Manage authentication
    config                      Open configuration file
    debug [mode]                Run system compatibility check
    models [options]            List available models

HINWEIS: Die interaktiven Befehle (/mode, /model, /checkpoint, /tasks, /teams, /new, /help, /exit)
werden innerhalb der interaktiven TUI-Sitzung verwendet und können nicht direkt über die CLI aufgerufen werden.
Für die Automatisierung sollten die CLI-Optionen verwendet werden.
"""

import subprocess
import json
import os
from typing import Optional, List, Dict, Any
from pathlib import Path


class KilocodeCliTool:
    """
    Python Wrapper für Kilocode CLI.
    
    Ermöglicht die Ausführung von Kilocode CLI-Befehlen aus Python heraus.
    """

    def __init__(self, kilocode_path: Optional[str] = None):
        """
        Initialisiert das Kilocode CLI Tool.
        
        Args:
            kilocode_path: Pfad zur kilocode.cmd Datei. Wenn None, wird versucht,
                          den Pfad automatisch zu finden.
        """
        if kilocode_path:
            self.kilocode_path = kilocode_path
        else:
            self.kilocode_path = self._find_kilocode_path()
        
        if not self.kilocode_path or not os.path.exists(self.kilocode_path):
            raise FileNotFoundError(
                f"Kilocode CLI nicht gefunden unter: {self.kilocode_path}\n"
                "Bitte installieren Sie Kilocode CLI mit: npm install -g @kilocode/cli"
            )

    def _find_kilocode_path(self) -> Optional[str]:
        """
        Sucht nach der kilocode.cmd Datei.
        
        Returns:
            Pfad zur kilocode.cmd oder None, wenn nicht gefunden.
        """
        # Prüfen, ob kilocode im PATH ist
        try:
            result = subprocess.run(
                ["where", "kilocode.cmd"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip().split('\n')[0]
        except Exception:
            pass
        
        # Prüfen Standardpfad für Windows
        npm_path = os.path.expandvars(r"%APPDATA%\npm\kilocode.cmd")
        if os.path.exists(npm_path):
            return npm_path
        
        return None

    def _run_command(
        self,
        args: List[str],
        capture_output: bool = True,
        timeout: Optional[int] = None
    ) -> subprocess.CompletedProcess:
        """
        Führt einen Kilocode CLI Befehl aus.
        
        Args:
            args: Liste der Argumente für kilocode.cmd
            capture_output: Ob die Ausgabe erfasst werden soll
            timeout: Timeout in Sekunden
            
        Returns:
            subprocess.CompletedProcess mit dem Ergebnis
        """
        cmd = [self.kilocode_path] + args
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                timeout=timeout
            )
            return result
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Command timeout after {timeout} seconds")
        except FileNotFoundError:
            raise FileNotFoundError(f"Kilocode CLI nicht gefunden: {self.kilocode_path}")

    def run_autonomous(
        self,
        prompt: str,
        workspace: Optional[str] = None,
        mode: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        timeout: Optional[int] = None,
        json_output: bool = False,
        yolo: bool = False,
        continue_session: bool = False,
        parallel: bool = False,
        existing_branch: Optional[str] = None,
        session_id: Optional[str] = None,
        attach_files: Optional[List[str]] = None,
        append_system_prompt: Optional[str] = None,
        on_task_completed: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Führt einen autonomen Kilocode-Befehl aus.
        
        Args:
            prompt: Der Prompt oder Befehl, der ausgeführt werden soll
            workspace: Pfad zum Workspace-Verzeichnis
            mode: Modus (architect, code, ask, debug, orchestrator, review)
            model: Modell-Override für den ausgewählten Provider
            provider: Provider-ID (z.B. 'kilocode-1')
            timeout: Timeout in Sekunden
            json_output: Ob die Ausgabe als JSON erfolgen soll
            yolo: Auto-approve aller Tool-Permissions
            continue_session: Ob die letzte Sitzung fortgesetzt werden soll
            parallel: Ob im Parallel-Modus ausgeführt werden soll
            existing_branch: Existierender Branch für Parallel-Modus
            session_id: Session-ID zum Wiederherstellen
            attach_files: Liste der Dateien, die angehängt werden sollen
            append_system_prompt: Zusätzliche System-Prompts
            on_task_completed: Prompt nach Aufgabenabschluss
            
        Returns:
            Dictionary mit stdout, stderr, returncode
        """
        args = []
        
        # Optionen hinzufügen
        if workspace:
            args.extend(["-w", workspace])
        if mode:
            args.extend(["-m", mode])
        if model:
            args.extend(["-M", model])
        if provider:
            args.extend(["-P", provider])
        if timeout:
            args.extend(["-t", str(timeout)])
        if json_output:
            args.append("-a")  # --auto ist erforderlich für --json
            args.append("-j")
        if yolo:
            args.append("-a")  # --auto ist erforderlich für --yolo
            args.append("--yolo")
        if continue_session:
            args.append("-c")
        if parallel:
            args.append("-p")
        if existing_branch:
            args.extend(["-e", existing_branch])
        if session_id:
            args.extend(["-s", session_id])
        if append_system_prompt:
            args.extend(["--append-system-prompt", append_system_prompt])
        if on_task_completed:
            args.extend(["--on-task-completed", on_task_completed])
        
        # Dateien anhängen
        if attach_files:
            for file_path in attach_files:
                args.extend(["--attach", file_path])
        
        # Prompt hinzufügen
        args.append(prompt)
        
        # Befehl ausführen
        result = self._run_command(args, timeout=timeout)
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "success": result.returncode == 0
        }

    def list_models(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """
        Listet verfügbare Modelle auf.
        
        Args:
            provider: Optionaler Provider-Filter
            
        Returns:
            Dictionary mit den Modellen als JSON
        """
        args = ["models"]
        if provider:
            args.extend(["-P", provider])
        
        result = self._run_command(args)
        
        if result.returncode == 0:
            try:
                models = json.loads(result.stdout)
                return {
                    "success": True,
                    "models": models
                }
            except json.JSONDecodeError:
                return {
                    "success": False,
                    "error": "Konnte Modelle nicht als JSON parsen",
                    "stdout": result.stdout
                }
        else:
            return {
                "success": False,
                "error": result.stderr,
                "returncode": result.returncode
            }

    def open_config(self) -> Dict[str, Any]:
        """
        Öffnet die Konfigurationsdatei im Standard-Editor.
        
        Returns:
            Dictionary mit dem Ergebnis
        """
        result = self._run_command(["config"], capture_output=False)
        
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode
        }

    def run_debug(self, mode: Optional[str] = None) -> Dict[str, Any]:
        """
        Führt einen System-Kompatibilitätscheck durch.
        
        Args:
            mode: Optionaler Debug-Modus
            
        Returns:
            Dictionary mit dem Ergebnis
        """
        args = ["debug"]
        if mode:
            args.append(mode)
        
        result = self._run_command(args)
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "success": result.returncode == 0
        }

    def get_version(self) -> Dict[str, Any]:
        """
        Gibt die Version von Kilocode CLI zurück.
        
        Returns:
            Dictionary mit der Version
        """
        result = self._run_command(["-V"])
        
        return {
            "version": result.stdout.strip(),
            "success": result.returncode == 0
        }

    def restore_session(self, session_id: str) -> Dict[str, Any]:
        """
        Stellt eine Sitzung anhand der ID wieder her.
        
        Args:
            session_id: Die Session-ID
            
        Returns:
            Dictionary mit dem Ergebnis
        """
        result = self._run_command(["-s", session_id])
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "success": result.returncode == 0
        }

    def fork_session(self, share_id: str) -> Dict[str, Any]:
        """
        Forkt eine Sitzung anhand der Share-ID.
        
        Args:
            share_id: Die Share-ID
            
        Returns:
            Dictionary mit dem Ergebnis
        """
        result = self._run_command(["-f", share_id])
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "success": result.returncode == 0
        }

    def to_autogen_tool(self):
        """
        Konvertiert das Tool in ein Autogen-kompatibles Tool.
        
        Returns:
            Ein Autogen-kompatibles Tool-Objekt
        """
        from autogen_core.tools import FunctionTool
        
        def run_kilocode_command(
            prompt: str,
            mode: Optional[str] = None,
            workspace: Optional[str] = None,
            timeout: Optional[int] = None,
            json_output: bool = False,
            yolo: bool = True,
            continue_session: bool = False,
            parallel: bool = False,
            existing_branch: Optional[str] = None,
            session_id: Optional[str] = None,
            attach_files: Optional[List[str]] = None,
            append_system_prompt: Optional[str] = None,
            on_task_completed: Optional[str] = None
        ) -> str:
            """
            Führt einen Kilocode CLI Befehl aus.
            
            Args:
                prompt: Der Prompt oder Befehl, der ausgeführt werden soll
                mode: Modus (architect, code, ask, debug, orchestrator, review)
                workspace: Pfad zum Workspace-Verzeichnis
                timeout: Timeout in Sekunden
                json_output: Ob die Ausgabe als JSON erfolgen soll
                yolo: Auto-approve aller Tool-Permissions (Standard: True für autonome Ausführung)
                continue_session: Ob die letzte Sitzung fortgesetzt werden soll
                parallel: Ob im Parallel-Modus ausgeführt werden soll
                existing_branch: Existierender Branch für Parallel-Modus
                session_id: Session-ID zum Wiederherstellen
                attach_files: Liste der Dateien, die angehängt werden sollen
                append_system_prompt: Zusätzliche System-Prompts
                on_task_completed: Prompt nach Aufgabenabschluss
                
            Returns:
                Das Ergebnis als String
            """
            result = self.run_autonomous(
                prompt=prompt,
                mode=mode,
                workspace=workspace,
                timeout=timeout,
                json_output=json_output,
                yolo=yolo,
                continue_session=continue_session,
                parallel=parallel,
                existing_branch=existing_branch,
                session_id=session_id,
                attach_files=attach_files,
                append_system_prompt=append_system_prompt,
                on_task_completed=on_task_completed
            )
            
            if result["success"]:
                return result["stdout"]
            else:
                return f"Fehler: {result['stderr']}"
        
        def list_kilocode_models_command(
            provider: Optional[str] = None
        ) -> str:
            """
            Listet verfügbare Kilocode Modelle auf.
            
            Args:
                provider: Optionaler Provider-Filter
                
            Returns:
                Die Modelle als JSON-String
            """
            result = self.list_models(provider=provider)
            
            if result["success"]:
                return json.dumps(result["models"], indent=2)
            else:
                return f"Fehler: {result['error']}"
        
        def get_kilocode_version_command() -> str:
            """
            Gibt die Version von Kilocode CLI zurück.
            
            Returns:
                Die Version als String
            """
            result = self.get_version()
            
            if result["success"]:
                return result["version"]
            else:
                return "Fehler: Version konnte nicht abgerufen werden"
        
        def restore_kilocode_session_command(
            session_id: str
        ) -> str:
            """
            Stellt eine Kilocode Sitzung wieder her.
            
            Args:
                session_id: Die Session-ID
                
            Returns:
                Das Ergebnis als String
            """
            result = self.restore_session(session_id)
            
            if result["success"]:
                return "Sitzung erfolgreich wiederhergestellt"
            else:
                return f"Fehler: {result['stderr']}"
        
        def fork_kilocode_session_command(
            share_id: str
        ) -> str:
            """
            Forkt eine Kilocode Sitzung.
            
            Args:
                share_id: Die Share-ID
                
            Returns:
                Das Ergebnis als String
            """
            result = self.fork_session(share_id)
            
            if result["success"]:
                return "Sitzung erfolgreich geforkt"
            else:
                return f"Fehler: {result['stderr']}"
        
        # Erstelle Autogen-Tools
        tools = [
            FunctionTool(
                run_kilocode_command,
                name="run_kilocode",
                description="Führt einen Kilocode CLI Befehl aus"
            ),
            FunctionTool(
                list_kilocode_models_command,
                name="list_kilocode_models",
                description="Listet verfügbare Kilocode Modelle auf"
            ),
            FunctionTool(
                get_kilocode_version_command,
                name="get_kilocode_version",
                description="Gibt die Version von Kilocode CLI zurück"
            ),
            FunctionTool(
                restore_kilocode_session_command,
                name="restore_kilocode_session",
                description="Stellt eine Kilocode Sitzung wieder her"
            ),
            FunctionTool(
                fork_kilocode_session_command,
                name="fork_kilocode_session",
                description="Forkt eine Kilocode Sitzung"
            )
        ]
        
        # Gib das erste Tool zurück (für die Kompatibilität mit dem bestehenden Code)
        return tools[0]


# Convenience-Funktionen für einfachere Verwendung

def run_kilocode(
    prompt: str,
    workspace: Optional[str] = None,
    mode: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Convenience-Funktion zum Ausführen eines Kilocode-Befehls.
    
    Args:
        prompt: Der Prompt oder Befehl
        workspace: Pfad zum Workspace
        mode: Modus (architect, code, ask, debug, orchestrator, review)
        **kwargs: Zusätzliche Argumente für run_autonomous
        
    Returns:
        Dictionary mit dem Ergebnis
    """
    tool = KilocodeCliTool()
    return tool.run_autonomous(prompt, workspace=workspace, mode=mode, **kwargs)


def list_kilocode_models(provider: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience-Funktion zum Auflisten der verfügbaren Modelle.
    
    Args:
        provider: Optionaler Provider-Filter
        
    Returns:
        Dictionary mit den Modellen
    """
    tool = KilocodeCliTool()
    return tool.list_models(provider=provider)


def get_kilocode_version() -> Dict[str, Any]:
    """
    Convenience-Funktion zum Abrufen der Kilocode-Version.
    
    Returns:
        Dictionary mit der Version
    """
    tool = KilocodeCliTool()
    return tool.get_version()


if __name__ == "__main__":
    # Beispiel: Version abrufen
    print("Kilocode CLI Version:")
    version_info = get_kilocode_version()
    print(version_info)
    
    # Beispiel: Modelle auflisten
    print("\nVerfügbare Modelle:")
    models_info = list_kilocode_models()
    print(json.dumps(models_info, indent=2))
