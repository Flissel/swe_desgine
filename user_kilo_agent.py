"""
User Kilo Agent - Erweiterter Agent für Kilo-CMD Befehle

Dieser Agent ermöglicht es Benutzern, Tasks mit CMD Commands an Kilo zu senden.
Er unterstützt verschiedene Modelle, einschließlich Z.AI: GLM 4.7 (free).
"""

import sys
import asyncio
import argparse

# Kodierung auf UTF-8 setzen für Windows-Kompatibilität
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from autogen_agentchat.agents import AssistantAgent
from openai import AsyncOpenAI
from ai_scientist.tools.kilocli_tool import KilocodeCliTool
from ai_scientist.tools.mermaid_output_handler import MermaidOutputHandler
from ai_scientist.tools.kilo_conversation import KiloConversationManager
from ai_scientist.tools.kilo_mermaid_bridge import KiloMermaidBridge
from interactive_shell import InteractiveShell
import re

# .env Datei laden
from dotenv import load_dotenv
load_dotenv()  # Lädt die .env Datei in die Umgebungsvariablen


class TerminationDetector:
    """Erkennt ob Kilocode-Task abgeschlossen ist."""

    COMPLETION_PATTERNS = [
        "TASK COMPLETE",
        "Aufgabe abgeschlossen",
        "Diagram erstellt",
        "Diagramm erstellt",
        "Mermaid generiert",
        "Datei gespeichert",
        "erfolgreich erstellt",
        "wurde erstellt",
        "fertig",
    ]

    @classmethod
    def is_task_complete(cls, response: str) -> bool:
        """Prüft ob Response Completion-Marker enthält."""
        response_lower = response.lower()
        for pattern in cls.COMPLETION_PATTERNS:
            if pattern.lower() in response_lower:
                return True
        return False

    @classmethod
    def extract_completion_info(cls, response: str) -> Dict[str, Any]:
        """Extrahiert Infos über abgeschlossene Task."""
        return {
            "complete": cls.is_task_complete(response),
            "mermaid_found": "```mermaid" in response or "flowchart" in response.lower(),
            "file_written": "gespeichert" in response.lower() or "saved" in response.lower(),
        }


class ResponseFilter:
    """Filtert und formatiert Kilo Agent Responses."""

    @staticmethod
    def clean_response(response_text: str) -> str:
        """Entfernt JSON-Spam und ANSI-Codes."""
        # 1. ANSI escape codes entfernen (erweitert für alle Varianten)
        # Standard CSI sequences: \x1b[...
        ansi_escape = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')
        response_text = ansi_escape.sub('', response_text)

        # OSC sequences: \x1b]...BEL oder ST
        osc_escape = re.compile(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?')
        response_text = osc_escape.sub('', response_text)

        # Andere escape sequences
        other_escape = re.compile(r'\x1b[()][AB012]')
        response_text = other_escape.sub('', response_text)

        # 2. JSON-Lines entfernen ({"timestamp":...})
        json_line = re.compile(r'\{"timestamp":\d+.*?\}\n?')
        response_text = json_line.sub('', response_text)

        # 3. Streaming-JSON entfernen
        streaming_json = re.compile(r'\{"type":"[^"]+","[^}]+\}\n?')
        response_text = streaming_json.sub('', response_text)

        # 4. Einzelne geschweifte Klammern am Zeilenanfang entfernen
        response_text = re.sub(r'^[}\]]\s*$', '', response_text, flags=re.MULTILINE)

        # 5. Leere Zeilen reduzieren
        response_text = re.sub(r'\n{3,}', '\n\n', response_text)

        return response_text.strip()

    @staticmethod
    def format_for_display(response_text: str, show_mermaid: bool = True) -> str:
        """Formatiert Response für Terminal-Anzeige - volle bereinigte Ausgabe."""
        # Mermaid extrahieren und hervorheben
        dtype, mermaid = MermaidOutputHandler.extract_mermaid_block(response_text)

        if mermaid and show_mermaid:
            # Entferne den Mermaid-Block aus dem Text für saubere Darstellung
            clean_text = re.sub(r'```mermaid[\s\S]*?```', '', response_text).strip()
            if clean_text:
                return f"{clean_text}\n\n✓ {dtype} Diagramm:\n```mermaid\n{mermaid}\n```"
            return f"✓ {dtype} Diagramm erstellt:\n\n```mermaid\n{mermaid}\n```"

        # Volle bereinigte Ausgabe ohne Kürzung
        return response_text




class UserKiloAgent:
    """
    Erweiterter User Agent für Kilo-CMD Befehle mit flexibler Konfiguration.
    """
    
    def __init__(
        self,
        model_name: str = "arcee-ai/trinity-large-preview:free",
        api_key: Optional[str] = None,
        base_url: Optional[str] = "https://openrouter.ai/api/v1",
        timeout: int = 300,
        workspace_dir: Optional[str] = None
    ):
        """
        Initialisiert den User Kilo Agent.
        
        Args:
            model_name: Name des zu verwendenden Modells (Standard: arcee-ai/trinity-large-preview:free)
            api_key: API Key für das Modell (optional, wird aus .env geladen)
            base_url: Base URL für die API (Standard: https://openrouter.ai/api/v1)
            timeout: Timeout in Sekunden für Kilo-Befehle (Standard: 300)
            workspace_dir: Arbeitsverzeichnis für Dateien (optional)
        """
        self.model_name = model_name
        # API Key aus Umgebungsvariablen laden, falls nicht angegeben
        if api_key is None:
            api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("ZAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.workspace_dir = Path(workspace_dir) if workspace_dir else Path.cwd()
        self.agent = None
        self.kilo_tool = None

        # Conversation History und Mermaid Bridge initialisieren
        self.conversation_manager = KiloConversationManager()
        self.mermaid_bridge = KiloMermaidBridge()

    async def initialize(self):
        """Initialisiert den Agenten und das Kilo Tool."""
        # API Key als Umgebungsvariable setzen (für OpenRouter Kompatibilität)
        if self.api_key:
            os.environ["OPENAI_API_KEY"] = self.api_key
        
        # Model Client erstellen (OpenAIChatCompletionClient für OpenRouter Kompatibilität)
        from autogen_ext.models.openai import OpenAIChatCompletionClient
        from autogen_core.models import ModelInfo
        
        # Model Info für OpenRouter Modelle erstellen
        model_info = ModelInfo(
            name=self.model_name,
            description="OpenRouter Model",
            vision=False,
            function_calling=True,
            json_output=True,
            structured_output=True,
            family="openrouter"
        )
        
        model_client = OpenAIChatCompletionClient(
            model=self.model_name,
            api_key=self.api_key,
            base_url=self.base_url,
            model_info=model_info
        )
        
        # Kilocode CLI Tool erstellen
        self.kilo_tool = KilocodeCliTool()
        
        # Autogen-Tools erstellen
        self.kilocode_tools = self.kilo_tool.to_autogen_tool()
        
        # Erweitertes System Message
        system_message = """Du bist ein autonomer User Agent, der Kilocode CLI-Befehle ausführen kann.

DEINE FUNKTIONEN:
- Führt Kilocode CLI-Befehle autonom aus, die der Benutzer angibt
- Analysiere Benutzeranfragen und führe entsprechende Kilocode CLI-Befehle aus
- Erkläre die Ergebnisse und gib Feedback
- Nutze die interaktive Shell für komplexe Aufgaben

VERFÜGBARE KILOCODE CLI-BEFEHLE:
Du hast Zugriff auf das kilocli Tool, das alle Kilocode CLI-Befehle unterstützt:

- run_kilocode: Führt einen Kilocode CLI Befehl aus (mit --auto Flag für autonome Ausführung)
- list_kilocode_models: Listet verfügbare Modelle auf
- get_kilocode_version: Gibt die Version von Kilocode CLI zurück
- restore_kilocode_session: Stellt eine Kilocode Sitzung wieder her
- fork_kilocode_session: Forkt eine Kilocode Sitzung

WICHTIGE CLI-OPTIONEN FÜR AUTONOME AUSFÜHRUNG:
- -a, --auto: Autonomer Modus (nicht interaktiv) - WIRD AUTOMATISCH VERWENDET
- -m, --mode <mode>: Modus setzen (architect, code, ask, debug, orchestrator, review)
- -w, --workspace <path>: Workspace-Pfad
- --yolo: Auto-approve aller Tool-Permissions (erfordert --auto)
- -j, --json: JSON-Ausgabe (erfordert --auto, wird automatisch hinzugefügt)
- -t, --timeout <seconds>: Timeout für autonomen Modus
- -p, --parallel: Parallel-Modus
- -P, --provider <id>: Provider auswählen
- -M, --model <model>: Modell-Override
- -s, --session <sessionId>: Sitzung wiederherstellen
- -f, --fork <shareId>: Sitzung forken
- --attach <path>: Datei anhängen

BEISPIELE:
1. Modus wechseln: "Wechsle in den Code-Modus"
2. Modelle auflisten: "Zeige mir alle verfügbaren Modelle an"
3. Modell auswählen: "Wähle das Modell gpt-4o aus"
4. Task-Historie anzeigen: "Zeige mir meine Tasks an"
5. Neue Aufgabe starten: "Starte eine neue Aufgabe: Erstelle eine Python-Funktion"
6. Mit Timeout: "Erstelle eine Funktion mit Timeout von 60 Sekunden"
7. Mit JSON-Ausgabe: "Führe den Befehl mit JSON-Ausgabe aus"

ARBEITSWEISE:
1. Verstehe die Benutzeranfrage
2. Bestimme den passenden Kilocode CLI-Befehl
3. Führe den Befehl mit dem kilocli Tool aus (automatisch mit --auto Flag)
4. Analysiere das Ergebnis
5. Gib eine klare Antwort zurück

FEHLERBEHANDLUNG:
- Wenn ein Befehl fehlschlägt, erkläre warum
- Schlage Alternativen vor
- Gib hilfreiche Fehlermeldungen zurück

AUTONOMIE:
- Du führst Befehle AUTOMATISCH mit der --auto Flag aus
- Du fragst nicht nach Bestätigung
- Du nutzt die --yolo Option, um alle Tool-Permissions automatisch zu genehmigen
- Du gibst Ergebnisse direkt zurück, ohne auf Benutzerinteraktion zu warten

WICHTIG: Wenn der Benutzer eine Datei erstellen möchte (z.B. "erstelle ein 4 mermaid für ein auth system basic"), dann sollst du dies mit dem run_kilocode Tool tun, nicht selbst versuchen, die Datei zu erstellen.

TASK COMPLETION (WICHTIG):
Wenn die Aufgabe erfüllt ist:
1. Schreibe "TASK COMPLETE" oder "Aufgabe abgeschlossen" am Ende deiner Antwort
2. Gib eine kurze Zusammenfassung was erstellt wurde
3. Falls Mermaid-Diagramm: Zeige das Diagramm mit ```mermaid ... ```
4. Verwende diese Begriffe bei Erfolg: "erstellt", "gespeichert", "fertig", "abgeschlossen"

MERMAID DIAGRAMME:
- Bei Mermaid-Erstellung immer den kompletten Code mit ```mermaid``` Block ausgeben
- Das Diagramm wird automatisch in der Datenbank gespeichert
- Diagrammtypen: flowchart, sequenceDiagram, classDiagram, stateDiagram, erDiagram, gantt

KONVERSATIONSKONTEXT:
- Du erhältst ggf. vorherigen Kontext aus der Gesprächshistorie
- Bei Follow-up-Anfragen wie "ändere das Diagramm" beziehe dich auf den vorherigen Kontext
- Die Session-ID ermöglicht iterative Änderungen an Diagrammen

"""
        
        # Agent erstellen
        self.agent = AssistantAgent(
            name="user_kilo_agent",
            model_client=model_client,
            tools=[self.kilocode_tools],
            system_message=system_message
        )
        
        print(f"\033[92m✓ User Kilo Agent initialisiert mit Modell:\033[0m \033[96m{self.model_name}\033[0m")
        
    async def execute_task(self, task: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Führt eine einzelne Aufgabe aus mit Termination-Check und Auto-Persistierung.

        Args:
            task: Die Aufgabe, die ausgeführt werden soll
            session_id: Optional Session-ID für Gesprächshistorie

        Returns:
            Dictionary mit dem Ergebnis inkl. task_complete und mermaid_id
        """
        if not self.agent:
            await self.initialize()

        # Session ID generieren falls nicht vorhanden
        if session_id is None:
            import uuid
            session_id = str(uuid.uuid4())[:8]

        # Conversation History laden
        conv = self.conversation_manager.get_or_create(session_id)
        conv.add_user_message(task)

        # Context aus History bauen (falls vorhanden)
        context = conv.get_context(max_messages=5)
        enhanced_task = task
        if len(conv.messages) > 1:
            enhanced_task = f"Vorheriger Kontext:\n{context}\n\n--- Neue Anfrage ---\n{task}"

        print(f"\n\033[94m📋 Aufgabe:\033[0m \033[96m{task}\033[0m")
        if len(conv.messages) > 1:
            print(f"\033[90m(Session: {session_id}, Nachrichten: {len(conv.messages)})\033[0m")
        print("-" * 60)

        try:
            response = await self.run(message=enhanced_task)
            
            # Extrahiere die Antwort aus der Response
            response_text = ""
            tool_calls_info = []  # Für ausgeführte Schritte

            # Prüfe verschiedene Response-Strukturen
            if response is not None:
                # AutoGen Response mit chat_message
                if hasattr(response, 'chat_message'):
                    msg = response.chat_message
                    if hasattr(msg, 'content'):
                        response_text = msg.content
                    # Extrahiere Tool-Calls Info
                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                        for tc in msg.tool_calls:
                            if hasattr(tc, 'name') and hasattr(tc, 'arguments'):
                                try:
                                    args = json.loads(tc.arguments) if isinstance(tc.arguments, str) else tc.arguments
                                    prompt = args.get('prompt', args.get('message', str(args)))
                                    tool_calls_info.append(f"🔧 {tc.name}: {prompt[:100]}...")
                                except:
                                    tool_calls_info.append(f"🔧 {tc.name}")
                # Response mit messages Liste
                elif hasattr(response, 'messages') and response.messages:
                    for msg in response.messages:
                        if hasattr(msg, 'content'):
                            response_text += msg.content + "\n"
                elif hasattr(response, 'content'):
                    response_text = response.content
                elif hasattr(response, 'message'):
                    response_text = response.message
                else:
                    response_text = str(response)

            # Extrahiere den eigentlichen Content aus verschachteltem JSON
            # Suche nach dem letzten "content":"..." Muster (die eigentliche Nachricht)
            content_matches = re.findall(r'"content"\s*:\s*"([^"]+)"', response_text)
            if content_matches:
                # Nimm den letzten nicht-hash Content (die eigentliche Nachricht)
                for match in reversed(content_matches):
                    # Ignoriere Hash-Werte (40 hex chars) und kurze Strings
                    if len(match) > 50 and not re.match(r'^[a-f0-9]{40}$', match):
                        response_text = match.replace('\\n', '\n').replace('\\r', '\r')
                        break
            else:
                response_text = "Keine Antwort vom Agent erhalten"
            
            # Versuche, JSON aus der Antwort zu extrahieren
            # Note: re and json are already imported at module level

            # Suche nach JSON-Objekt in der Antwort
            json_match = re.search(r'\{[^{}]*"stdout"[^{}]*"stderr"[^{}]*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    result_json = json.loads(json_match.group())
                    # Extrahiere stdout oder stderr mit MermaidOutputHandler
                    if 'stdout' in result_json and result_json['stdout']:
                        stdout = MermaidOutputHandler.unescape_content(result_json['stdout'])
                        # Fix malformed mermaid markdown if needed
                        stdout = MermaidOutputHandler.fix_malformed_markdown(stdout)
                        response_text = stdout.strip()
                    elif 'stderr' in result_json and result_json['stderr']:
                        stderr = MermaidOutputHandler.unescape_content(result_json['stderr'])
                        response_text = stderr.strip()
                    elif 'success' in result_json and result_json['success']:
                        # Wenn success vorhanden ist, prüfe auf stdout
                        if 'stdout' in result_json and result_json['stdout']:
                            stdout = MermaidOutputHandler.unescape_content(result_json['stdout'])
                            stdout = MermaidOutputHandler.fix_malformed_markdown(stdout)
                            response_text = stdout.strip()
                        elif 'stderr' in result_json and result_json['stderr']:
                            stderr = MermaidOutputHandler.unescape_content(result_json['stderr'])
                            response_text = stderr.strip()
                except:
                    pass
            
            # Wenn immer noch leer, versuche den content aus der Response zu extrahieren
            if not response_text.strip():
                # Versuche, den content aus der Response zu extrahieren
                content_match = re.search(r'content\s*=\s*[\'"]([^\'\"]+)[\'"]', str(response))
                if content_match:
                    response_text = content_match.group(1)
            
            # Wenn immer noch leer, versuche Error-Nachricht zu extrahieren
            if not response_text.strip():
                error_match = re.search(r'Error:\s*([^\n]+)', response_text)
                if error_match:
                    response_text = error_match.group(1).strip()
            
            # Wenn immer noch leer, versuche tool 'echo' not found zu extrahieren
            if not response_text.strip():
                tool_error_match = re.search(r"tool '([^']+)' not found", response_text)
                if tool_error_match:
                    response_text = f"Tool '{tool_error_match.group(1)}' nicht gefunden"
            
            # Wenn immer noch leer, versuche tool 'echo' not found in any workbench zu extrahieren
            if not response_text.strip():
                tool_error_match2 = re.search(r"tool '([^']+)' not found in any workbench", response_text)
                if tool_error_match2:
                    response_text = f"Tool '{tool_error_match2.group(1)}' nicht gefunden"
            
            # Wenn immer noch leer, versuche Befehl nicht gefunden zu extrahieren
            if not response_text.strip():
                command_error_match = re.search(r"Befehl '([^']+)' nicht gefunden", response_text)
                if command_error_match:
                    response_text = f"Befehl '{command_error_match.group(1)}' nicht gefunden"
            
            # Wenn immer noch leer, versuche stderr aus dem JSON zu extrahieren
            if not response_text.strip():
                stderr_match = re.search(r'"stderr"\s*:\s*"([^"]*)"', response_text)
                if stderr_match:
                    stderr = stderr_match.group(1).replace('\\n', '\n').replace('\\r', '\r').strip()
                    response_text = stderr
            
            # Wenn immer noch leer, versuche stderr aus dem JSON zu extrahieren (mit escaped quotes)
            if not response_text.strip():
                stderr_match2 = re.search(r'"stderr"\s*:\s*\\"([^"]*)\\"', response_text)
                if stderr_match2:
                    stderr = stderr_match2.group(1).replace('\\n', '\n').replace('\\r', '\r').strip()
                    response_text = stderr
            
            # Response filtern und bereinigen
            response_text = ResponseFilter.clean_response(response_text)

            # Termination Check
            completion = TerminationDetector.extract_completion_info(response_text)

            # Mermaid Auto-Persist
            mermaid_id = None
            if completion["mermaid_found"]:
                mermaid_id = self.mermaid_bridge.save_from_kilo_output(
                    response=response_text,
                    title=task[:50],
                    session_id=session_id,
                )
                if mermaid_id:
                    print(f"\033[92m💾 Mermaid gespeichert: {mermaid_id}\033[0m")

            # Response zur History hinzufügen
            conv.add_agent_response(response_text, mermaid_id=mermaid_id)

            result = {
                "success": True,
                "task": task,
                "response": response_text.strip(),
                "model": self.model_name,
                "task_complete": completion["complete"],
                "mermaid_id": mermaid_id,
                "session_id": session_id,
            }

            # Ausgabe mit Farben und Icons formatieren
            print(f"\n\033[92m✓ Agent-Antwort:\033[0m")
            print("-" * 60)

            # Zeige ausgeführte Schritte
            if tool_calls_info:
                print(f"\033[93m📋 Ausgeführte Schritte:\033[0m")
                for step in tool_calls_info:
                    print(f"  {step}")
                print()

            if response_text.strip():
                # Format für Display
                display_text = ResponseFilter.format_for_display(response_text)
                print(f"\033[96m{display_text}\033[0m")  # Cyan für die Antwort
            else:
                print("\033[93mKeine Antwort erhalten\033[0m")  # Gelb für keine Antwort
            print("-" * 60)

            if completion["complete"]:
                print(f"\033[92m✓ Task abgeschlossen\033[0m")

            return result
            
        except Exception as e:
            result = {
                "success": False,
                "task": task,
                "error": str(e),
                "model": self.model_name
            }
            
            print(f"\n\033[91m✗ Fehler:\033[0m \033[93m{str(e)}\033[0m")  # Rot für Fehler, Gelb für Nachricht
            
            return result
    
    async def run(self, message: str):
        """Führt eine Nachricht an den Agenten aus."""
        from autogen_agentchat.messages import TextMessage
        msg = TextMessage(content=message, source="user")
        response = await self.agent.on_messages([msg], cancellation_token=None)
        return response
    
    async def execute_batch_tasks(self, tasks: List[str]) -> List[Dict[str, Any]]:
        """
        Führt mehrere Aufgaben nacheinander aus.
        
        Args:
            tasks: Liste der Aufgaben
            
        Returns:
            Liste der Ergebnisse
        """
        results = []
        
        for i, task in enumerate(tasks, 1):
            print(f"\n\033[95m{'='*60}\033[0m")
            print(f"\033[95mAufgabe {i}/{len(tasks)}\033[0m")
            print(f"\033[95m{'='*60}\033[0m")
            
            result = await self.execute_task(task)
            results.append(result)
            
        return results
    
    def save_result(self, result: Dict[str, Any], filename: Optional[str] = None):
        """
        Speichert ein Ergebnis in einer JSON-Datei.
        
        Args:
            result: Das zu speichernde Ergebnis
            filename: Dateiname (optional)
        """
        if filename is None:
            timestamp = asyncio.get_event_loop().time()
            filename = f"kilo_result_{int(timestamp)}.json"
        
        filepath = self.workspace_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n\033[92m💾 Ergebnis gespeichert:\033[0m \033[96m{filepath}\033[0m")
    
    def load_config(self, config_path: str) -> Dict[str, Any]:
        """
        Lädt eine Konfiguration aus einer JSON-Datei.
        
        Args:
            config_path: Pfad zur Konfigurationsdatei
            
        Returns:
            Konfigurations-Dictionary
        """
        filepath = Path(config_path)
        
        if not filepath.exists():
            raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden: {config_path}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        print(f"\033[92m✓ Konfiguration geladen:\033[0m \033[96m{config_path}\033[0m")
        
        return config
    
    async def execute_from_config(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Führt Aufgaben basierend auf einer Konfiguration aus.
        
        Args:
            config: Konfigurations-Dictionary mit 'tasks' Liste
            
        Returns:
            Liste der Ergebnisse
        """
        tasks = config.get('tasks', [])
        
        if not tasks:
            print("\033[93m⚠ Keine Aufgaben in der Konfiguration gefunden\033[0m")
            return []
        
        print(f"\033[94m📋 Führe\033[0m \033[96m{len(tasks)}\033[0m \033[94mAufgaben aus der Konfiguration aus\033[0m")
        
        return await self.execute_batch_tasks(tasks)
    
    async def run_interactive_shell(self):
        """
        Startet die interaktive Shell für komplexe Aufgabenverwaltung.
        
        Die interaktive Shell ermöglicht es, Aufgaben mit Prioritäten zu verwalten,
        Ergebnisse anzuzeigen und Aufgaben zu speichern und zu laden.
        """
        print(f"\n\033[95m{'='*60}\033[0m")
        print(f"\033[95mInteraktive Shell für User Kilo Agent\033[0m")
        print(f"\033[95m{'='*60}\033[0m")
        
        # Interaktive Shell starten
        from interactive_shell import run_interactive_shell as run_shell
        await run_shell(workspace_dir=str(self.workspace_dir))
    
    async def execute_with_shell(self, task: str, priority: int = 1) -> Dict[str, Any]:
        """
        Führt eine Aufgabe mit der interaktiven Shell aus.
        
        Args:
            task: Die Aufgabe, die ausgeführt werden soll
            priority: Priorität der Aufgabe (0=niedrig, 1=mittel, 2=hoch)
            
        Returns:
            Dictionary mit dem Ergebnis
        """
        # Interaktive Shell erstellen
        shell = InteractiveShell()
        
        # Aufgabe hinzufügen
        task_index = shell.add_task(task, priority)
        
        # Nächste Aufgabe abrufen
        next_task = shell.get_next_task()
        
        if next_task:
            # Aufgabe ausführen
            result = await self.execute_task(next_task["task"])
            
            # Ergebnis aktualisieren
            shell.update_task_result(task_index, result)
            
            return result
        else:
            return {
                "success": False,
                "task": task,
                "error": "Keine Aufgabe zum Ausführen gefunden"
            }


async def create_user_kilo_agent(
    model_name: str = "arcee-ai/trinity-large-preview:free",
    api_key: Optional[str] = None,
    base_url: Optional[str] = "https://openrouter.ai/api/v1",
    timeout: int = 300,
    workspace_dir: Optional[str] = None
) -> UserKiloAgent:
    """
    Erstellt und initialisiert einen User Kilo Agent.
    
    Args:
        model_name: Name des zu verwendenden Modells (Standard: arcee-ai/trinity-large-preview:free)
        api_key: API Key für das Modell (optional, wird aus .env geladen)
        base_url: Base URL für die API (Standard: https://openrouter.ai/api/v1)
        timeout: Timeout in Sekunden
        workspace_dir: Arbeitsverzeichnis
        
    Returns:
        Initialisierter UserKiloAgent
    """
    agent = UserKiloAgent(
        model_name=model_name,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        workspace_dir=workspace_dir
    )
    
    await agent.initialize()
    
    return agent


async def run_interactive_session(
    model_name: str = "arcee-ai/trinity-large-preview:free",
    api_key: Optional[str] = None,
    base_url: Optional[str] = "https://openrouter.ai/api/v1",
    timeout: int = 300,
    workspace_dir: Optional[str] = None
):
    """
    Führt eine interaktive Sitzung mit dem User Kilo Agent durch.
    
    Args:
        model_name: Name des zu verwendenden Modells (Standard: arcee-ai/trinity-large-preview:free)
        api_key: API Key für das Modell (optional, wird aus .env geladen)
        base_url: Base URL für die API (Standard: https://openrouter.ai/api/v1)
        timeout: Timeout in Sekunden
        workspace_dir: Arbeitsverzeichnis
    """
    print(f"\033[95m{'='*60}\033[0m")
    print(f"\033[96m🤖 User Kilo Agent - Interaktive Sitzung\033[0m")
    print(f"\033[95m{'='*60}\033[0m")
    print(f"\033[94mModell:\033[0m \033[96m{model_name}\033[0m")
    print("\033[94mGeben Sie 'exit', 'quit' oder 'beenden' ein, um die Sitzung zu beenden.\033[0m")
    print("\033[94mGeben Sie 'help' ein, um verfügbare Befehle zu sehen.\033[0m")
    print(f"\033[95m{'='*60}\033[0m\n")
    
    # Agent erstellen
    agent = await create_user_kilo_agent(
        model_name=model_name,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        workspace_dir=workspace_dir
    )
    
    # Interaktive Schleife
    while True:
        try:
            # Benutzereingabe
            user_input = input("Sie: ").strip()
            
            if user_input.lower() in ['exit', 'quit', 'beenden']:
                print("\n\033[92m👋 Auf Wiedersehen!\033[0m")
                break
            
            if user_input.lower() == 'help':
                print("\n\033[94m📚 Verfügbare Befehle:\033[0m")
                print("  \033[96m- 'Zeige mir die Hilfe für Kilo'\033[0m")
                print("  \033[96m- 'Zeige mir die Version von Kilo'\033[0m")
                print("  \033[96m- 'Führe kilo mit --help aus'\033[0m")
                print("  \033[96m- 'Was kann Kilo tun?'\033[0m")
                print("  \033[96m- 'exit', 'quit', 'beenden' - Sitzung beenden\033[0m")
                print("  \033[96m- 'help' - Diese Hilfe anzeigen\033[0m")
                print()
                continue
            
            if not user_input:
                continue
            
            # Nachricht an den Agenten senden
            result = await agent.execute_task(user_input)
            
            # Ergebnis speichern
            if result["success"]:
                agent.save_result(result)
            
        except KeyboardInterrupt:
            print("\n\n\033[92m👋 Auf Wiedersehen!\033[0m")
            break
        except Exception as e:
            print(f"\n\033[91m✗ Fehler:\033[0m \033[93m{str(e)}\033[0m\n")


async def run_single_task(
    task: str,
    model_name: str = "arcee-ai/trinity-large-preview:free",
    api_key: Optional[str] = None,
    base_url: Optional[str] = "https://openrouter.ai/api/v1",
    timeout: int = 300,
    workspace_dir: Optional[str] = None,
    save_result: bool = True
):
    """
    Führt eine einzelne Aufgabe mit dem User Kilo Agent durch.
    
    Args:
        task: Die Aufgabe, die ausgeführt werden soll
        model_name: Name des zu verwendenden Modells (Standard: arcee-ai/trinity-large-preview:free)
        api_key: API Key für das Modell (optional, wird aus .env geladen)
        base_url: Base URL für die API (Standard: https://openrouter.ai/api/v1)
        timeout: Timeout in Sekunden
        workspace_dir: Arbeitsverzeichnis
        save_result: Ob das Ergebnis gespeichert werden soll
    """
    print(f"\033[95m{'='*60}\033[0m")
    print(f"\033[96m🤖 User Kilo Agent - Aufgabe\033[0m")
    print(f"\033[95m{'='*60}\033[0m")
    print(f"\033[94mModell:\033[0m \033[96m{model_name}\033[0m")
    print(f"\033[94mAufgabe:\033[0m \033[96m{task}\033[0m")
    print(f"\033[95m{'='*60}\033[0m\n")
    
    # Agent erstellen
    agent = await create_user_kilo_agent(
        model_name=model_name,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        workspace_dir=workspace_dir
    )
    
    # Aufgabe ausführen
    result = await agent.execute_task(task)
    
    # Ergebnis speichern
    if save_result and result["success"]:
        agent.save_result(result)
    
    return result


async def run_from_config(
    config_path: str,
    model_name: str = "arcee-ai/trinity-large-preview:free",
    api_key: Optional[str] = None,
    base_url: Optional[str] = "https://openrouter.ai/api/v1",
    timeout: int = 300,
    workspace_dir: Optional[str] = None
):
    """
    Führt Aufgaben aus einer Konfigurationsdatei aus.
    
    Args:
        config_path: Pfad zur Konfigurationsdatei
        model_name: Name des zu verwendenden Modells (Standard: arcee-ai/trinity-large-preview:free)
        api_key: API Key für das Modell (optional, wird aus .env geladen)
        base_url: Base URL für die API (Standard: https://openrouter.ai/api/v1)
        timeout: Timeout in Sekunden
        workspace_dir: Arbeitsverzeichnis
    """
    print(f"\033[95m{'='*60}\033[0m")
    print(f"\033[96m🤖 User Kilo Agent - Konfigurationsmodus\033[0m")
    print(f"\033[95m{'='*60}\033[0m")
    print(f"\033[94mModell:\033[0m \033[96m{model_name}\033[0m")
    print(f"\033[94mKonfiguration:\033[0m \033[96m{config_path}\033[0m")
    print(f"\033[95m{'='*60}\033[0m\n")
    
    # Agent erstellen
    agent = await create_user_kilo_agent(
        model_name=model_name,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        workspace_dir=workspace_dir
    )
    
    # Konfiguration laden
    config = agent.load_config(config_path)
    
    # Aufgaben ausführen
    results = await agent.execute_from_config(config)
    
    # Zusammenfassung
    print("\n" + f"\033[95m{'='*60}\033[0m")
    print(f"\033[94m📊 Zusammenfassung\033[0m")
    print(f"\033[95m{'='*60}\033[0m")
    successful = sum(1 for r in results if r["success"])
    failed = len(results) - successful
    print(f"\033[92mErfolgreich:\033[0m \033[96m{successful}/{len(results)}\033[0m")
    print(f"\033[91mFehlgeschlagen:\033[0m \033[96m{failed}/{len(results)}\033[0m")
    print(f"\033[95m{'='*60}\033[0m")
    
    return results


async def run_interactive_shell(
    model_name: str = "arcee-ai/trinity-large-preview:free",
    api_key: Optional[str] = None,
    base_url: Optional[str] = "https://openrouter.ai/api/v1",
    timeout: int = 300,
    workspace_dir: Optional[str] = None
):
    """
    Startet die interaktive Shell für komplexe Aufgabenverwaltung.
    
    Args:
        model_name: Name des zu verwendenden Modells (Standard: arcee-ai/trinity-large-preview:free)
        api_key: API Key für das Modell (optional, wird aus .env geladen)
        base_url: Base URL für die API (Standard: https://openrouter.ai/api/v1)
        timeout: Timeout in Sekunden
        workspace_dir: Arbeitsverzeichnis
    """
    print(f"\033[95m{'='*60}\033[0m")
    print(f"\033[96m🤖 User Kilo Agent - Interaktive Shell\033[0m")
    print(f"\033[95m{'='*60}\033[0m")
    print(f"\033[94mModell:\033[0m \033[96m{model_name}\033[0m")
    print(f"\033[95m{'='*60}\033[0m\n")
    
    # Interaktive Shell direkt starten
    from interactive_shell import run_interactive_shell as run_shell
    await run_shell(workspace_dir=workspace_dir)


def main():
    """
    Hauptfunktion zum Ausführen des User Kilo Agent.
    """
    parser = argparse.ArgumentParser(
        description="User Kilo Agent - Erweiterter Agent für Kilo-CMD Befehle"
    )
    
    parser.add_argument(
        "--task",
        type=str,
        help="Einzelne Aufgabe, die ausgeführt werden soll"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        help="Pfad zur Konfigurationsdatei (JSON)"
    )
    
    parser.add_argument(
        "--model",
        type=str,
        default="arcee-ai/trinity-large-preview:free",
        help="Name des zu verwendenden Modells (Standard: arcee-ai/trinity-large-preview:free)"
    )
    
    parser.add_argument(
        "--base-url",
        type=str,
        default="https://openrouter.ai/api/v1",
        help="Base URL für die API (Standard: https://openrouter.ai/api/v1)"
    )
    
    parser.add_argument(
        "--api-key",
        type=str,
        help="API Key für das Modell"
    )
    
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout in Sekunden für Kilo-Befehle (Standard: 300)"
    )
    
    parser.add_argument(
        "--workspace",
        type=str,
        help="Arbeitsverzeichnis für Dateien (optional)"
    )
    
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Startet eine interaktive Sitzung"
    )
    
    parser.add_argument(
        "--shell",
        action="store_true",
        help="Startet die interaktive Shell für komplexe Aufgabenverwaltung"
    )
    
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Ergebnisse nicht speichern"
    )
    
    args = parser.parse_args()
    
    if args.shell:
        # Interaktive Shell starten
        asyncio.run(run_interactive_shell(
            model_name=args.model,
            api_key=args.api_key,
            base_url=args.base_url,
            timeout=args.timeout,
            workspace_dir=args.workspace
        ))
    elif args.interactive:
        asyncio.run(run_interactive_session(
            model_name=args.model,
            api_key=args.api_key,
            base_url=args.base_url,
            timeout=args.timeout,
            workspace_dir=args.workspace
        ))
    elif args.config:
        asyncio.run(run_from_config(
            config_path=args.config,
            model_name=args.model,
            api_key=args.api_key,
            base_url=args.base_url,
            timeout=args.timeout,
            workspace_dir=args.workspace
        ))
    elif args.task:
        asyncio.run(run_single_task(
            task=args.task,
            model_name=args.model,
            api_key=args.api_key,
            base_url=args.base_url,
            timeout=args.timeout,
            workspace_dir=args.workspace,
            save_result=not args.no_save
        ))
    else:
        # Standard: Interaktive Sitzung
        asyncio.run(run_interactive_session(
            model_name=args.model,
            api_key=args.api_key,
            base_url=args.base_url,
            timeout=args.timeout,
            workspace_dir=args.workspace
        ))


if __name__ == "__main__":
    main()
