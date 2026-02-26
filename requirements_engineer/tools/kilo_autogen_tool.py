"""
Kilo AutoGen 0.4 Tool

Dieses Modul stellt den Kilo-Agenten als exportierbares AutoGen 0.4 Tool bereit,
das direkt in AutoGen 0.4 Projekten verwendet werden kann.
"""

from typing import Any, Dict, List
from autogen_core.tools import FunctionTool
from autogen_ext.models import OpenAIChatCompletionClient
import subprocess
import json
import logging

logger = logging.getLogger(__name__)


class KiloAutoGenTool:
    """
    Kilo AutoGen 0.4 Tool für die direkte Verwendung in AutoGen 0.4 Projekten.
    
    Dieses Tool kann direkt als FunctionTool in AutoGen 0.4 verwendet werden,
    ohne dass ein separater Agent erstellt werden muss.
    """
    
    def __init__(self, timeout: int = 300):
        """
        Initialisiert das Kilo AutoGen Tool.
        
        Args:
            timeout: Timeout in Sekunden für Kilo-Befehle (Standard: 300)
        """
        self.timeout = timeout
        self.kilo_command = "kilo"
    
    def execute_kilo_command(
        self,
        command: str = "kilo",
        parameters: List[str] = None
    ) -> str:
        """
        Führt einen Kilo-CMD-Befehl aus und gibt das Ergebnis zurück.
        
        Args:
            command: Der Kilo-Befehl (Standard: "kilo")
            parameters: Liste der Parameter für den Befehl
            
        Returns:
            String mit dem Ergebnis des Kilo-Befehls
        """
        if parameters is None:
            parameters = []
        
        # Befehl zusammenbauen
        cmd_list = [command] + parameters
        
        logger.info(f"Führe Kilo-Befehl aus: {' '.join(cmd_list)}")
        
        try:
            # Befehl ausführen
            result = subprocess.run(
                cmd_list,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            # Ergebnis formatieren
            if result.returncode == 0:
                output = f"✓ Erfolgreich: {result.stdout}"
            else:
                output = f"✗ Fehlgeschlagen: {result.stderr}"
            
            logger.info(output)
            return output
            
        except subprocess.TimeoutExpired:
            error_msg = f"✗ Timeout nach {self.timeout} Sekunden"
            logger.error(error_msg)
            return error_msg
        except FileNotFoundError:
            error_msg = f"✗ Befehl '{command}' nicht gefunden"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"✗ Unerwarteter Fehler: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    def get_kilo_help(self) -> str:
        """
        Ruft die Hilfe für Kilo ab.
        
        Returns:
            String mit der Kilo-Hilfe
        """
        return self.execute_kilo_command(command="kilo", parameters=["--help"])
    
    def get_kilo_version(self) -> str:
        """
        Ruft die Version von Kilo ab.
        
        Returns:
            String mit der Kilo-Version
        """
        return self.execute_kilo_command(command="kilo", parameters=["--version"])


def create_kilo_autogen_tool(timeout: int = 300) -> FunctionTool:
    """
    Erstellt ein AutoGen 0.4 FunctionTool für Kilo-CMD-Befehle.
    
    Args:
        timeout: Timeout in Sekunden für Kilo-Befehle (Standard: 300)
        
    Returns:
        FunctionTool für die Verwendung in AutoGen 0.4
    """
    kilo_tool = KiloAutoGenTool(timeout=timeout)
    
    return FunctionTool(
        name="kilo_cmd",
        description="Führt Kilo-CMD-Befehle mit Parametern aus. Parameter: command (str, Standard: 'kilo'), parameters (list[str], optional: Liste der Parameter für den Befehl. Gibt das Ergebnis des Befehls zurück.",
        func=kilo_tool.execute_kilo_command
    )


def create_kilo_help_tool(timeout: int = 300) -> FunctionTool:
    """
    Erstellt ein AutoGen 0.4 FunctionTool für Kilo-Hilfe.
    
    Args:
        timeout: Timeout in Sekunden (Standard: 300)
        
    Returns:
        FunctionTool für die Verwendung in AutoGen 0.4
    """
    kilo_tool = KiloAutoGenTool(timeout=timeout)
    
    return FunctionTool(
        name="kilo_help",
        description="Zeigt die Hilfe für Kilo an. Gibt die Kilo-Hilfe zurück.",
        func=kilo_tool.get_kilo_help
    )


def create_kilo_version_tool(timeout: int = 300) -> FunctionTool:
    """
    Erstellt ein AutoGen 0.4 FunctionTool für Kilo-Version.
    
    Args:
        timeout: Timeout in Sekunden (Standard: 300)
        
    Returns:
        FunctionTool für die Verwendung in AutoGen 0.4
    """
    kilo_tool = KiloAutoGenTool(timeout=timeout)
    
    return FunctionTool(
        name="kilo_version",
        description="Zeigt die Version von Kilo an. Gibt die Kilo-Version zurück.",
        func=kilo_tool.get_kilo_version
    )


def create_all_kilo_tools(timeout: int = 300) -> List[FunctionTool]:
    """
    Erstellt alle Kilo AutoGen 0.4 Tools.
    
    Args:
        timeout: Timeout in Sekunden für Kilo-Befehle (Standard: 300)
        
    Returns:
        Liste aller Kilo FunctionTools
    """
    return [
        create_kilo_autogen_tool(timeout),
        create_kilo_help_tool(timeout),
        create_kilo_version_tool(timeout),
    ]


# Beispiel für die Verwendung in AutoGen 0.4
if __name__ == "__main__":
    # Beispiel: Erstellen eines Agents mit Kilo-Tools
    from autogen_agentchat.agents import AssistantAgent
    from autogen_ext.models import OpenAIChatCompletionClient
    
    # Model Client erstellen
    model_client = OpenAIChatCompletionClient(
        model="gpt-4o-mini",
        api_key="your-api-key"
    )
    
    # Kilo-Tools erstellen
    kilo_tools = create_all_kilo_tools(timeout=300)
    
    # Agent erstellen
    agent = AssistantAgent(
        name="kilo_agent",
        model_client=model_client,
        tools=kilo_tools,
        system_message="""Du bist ein hilfreicher Assistent, der Kilo-CMD-Befehle ausführen kann.
Du hast Zugriff auf folgende Tools:
- kilo_cmd: Führt Kilo-Befehle mit Parametern aus
- kilo_help: Zeigt die Hilfe für Kilo an
- kilo_version: Zeigt die Version von Kilo an

Verwende diese Tools, um die Anfragen des Benutzers zu erfüllen."""
    )
    
    print("Kilo AutoGen 0.4 Tools erstellt!")
    print("Verfügbare Tools:")
    for tool in kilo_tools:
        print(f"  - {tool.name}: {tool.description}")
