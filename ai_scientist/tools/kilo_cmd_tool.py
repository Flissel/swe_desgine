"""
Kilo CMD Tool für AutoGen 0.4

Dieses Tool ermöglicht es einem AutoGen-Agenten, Befehle auszuführen.
Es unterstützt strukturierte Ausgabe und eine interaktive Shell, wo man Tasks senden kann.
"""

import subprocess
import json
import sys
from typing import Any, Dict, List, Optional
from .base_tool import BaseTool


class KiloCmdTool(BaseTool):
    """
    Tool zum Ausführen von Befehlen.
    
    Dieses Tool ermöglicht es einem AutoGen-Agenten, Befehle mit Parametern
    auszuführen und die Ergebnisse zurückzugeben.
    
    Es unterstützt strukturierte Ausgabe und eine interaktive Shell, wo man Tasks senden kann.
    """
    
    def __init__(self):
        parameters = [
            {
                "name": "command",
                "type": "string",
                "description": "Der Befehl, der ausgeführt werden soll (z.B. 'python', 'echo', 'ls')"
            },
            {
                "name": "parameters",
                "type": "list",
                "description": "Liste der Parameter für den Befehl (z.B. ['--version', 'Hallo Welt'])"
            },
            {
                "name": "structured_output",
                "type": "boolean",
                "description": "Ob die Ausgabe strukturiert als JSON zurückgegeben werden soll (Standard: False)"
            }
        ]
        
        super().__init__(
            name="kilo_cmd",
            description="Führt Befehle mit Parametern aus und gibt das Ergebnis zurück. Unterstützt strukturierte Ausgabe und interaktive Shell.",
            parameters=parameters
        )
    
    def use_tool(self, command: str = "kilo", parameters: List[str] = None, structured_output: bool = False, **kwargs) -> Dict[str, Any]:
        """
        Führt einen Befehl aus.
        
        Args:
            command: Der Befehl (Standard: 'kilo')
            parameters: Liste der Parameter für den Befehl
            structured_output: Ob die Ausgabe strukturiert als JSON zurückgegeben werden soll (Standard: False)
            
        Returns:
            Dict mit 'success', 'stdout', 'stderr', 'return_code', 'command'
        """
        if parameters is None:
            parameters = []
        
        # Befehl zusammenbauen
        cmd_list = [command] + parameters
        
        # Für Windows: shell=True verwenden, um Befehle wie echo zu unterstützen
        shell = sys.platform == 'win32'
        
        try:
            # Befehl ausführen
            result = subprocess.run(
                cmd_list,
                capture_output=True,
                text=True,
                timeout=300,  #5 Minuten Timeout
                shell=shell
            )
            
            # Strukturierte Ausgabe
            if structured_output:
                return {
                    "success": result.returncode == 0,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "return_code": result.returncode,
                    "command": " ".join(cmd_list),
                    "structured": True
                }
            else:
                return {
                    "success": result.returncode == 0,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "return_code": result.returncode,
                    "command": " ".join(cmd_list)
                }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Befehl Timeout nach 5 Minuten",
                "return_code": -1,
                "command": " ".join(cmd_list)
            }
        except FileNotFoundError:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Befehl '{command}' nicht gefunden.",
                "return_code": -1,
                "command": " ".join(cmd_list)
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Unerwarteter Fehler: {str(e)}",
                "return_code": -1,
                "command": " ".join(cmd_list)
            }
    
    def to_autogen_tool(self):
        """
        Konvertiert das Tool in das AutoGen 0.4 Format.
        
        Returns:
            AutoGen Tool Definition
        """
        from autogen_core.tools import FunctionTool
        
        def execute_command(command: str = "kilo", parameters: List[str] = None, structured_output: bool = False) -> str:
            """Führt einen Befehl aus.
            
            Args:
                command: Der Befehl (Standard: 'kilo')
                parameters: Liste der Parameter für den Befehl
                structured_output: Ob die Ausgabe strukturiert als JSON zurückgegeben werden soll (Standard: False)
                
            Returns:
                JSON-String mit dem Ergebnis
            """
            result = self.use_tool(command=command, parameters=parameters, structured_output=structured_output)
            return json.dumps(result, indent=2, ensure_ascii=False)
        
        return FunctionTool(
            execute_command,
            name=self.name,
            description=self.description
        )
