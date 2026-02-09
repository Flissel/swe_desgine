"""
Kilo Agent Integration für AI-Scientist

Dieses Modul integriert den Kilo-Agenten in das AI-Scientist-System,
um Kilo-CMD-Befehle während der Experimentausführung zu ermöglichen.
"""

import json
import subprocess
from typing import Dict, Any, Optional, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class KiloAgentIntegration:
    """
    Integration des Kilo-Agenten in das AI-Scientist-System.
    
    Diese Klasse ermöglicht es dem AI-Scientist, Kilo-CMD-Befehle
    während der Experimentausführung auszuführen.
    """
    
    def __init__(self, workspace_dir: Path):
        """
        Initialisiert die Kilo-Agent-Integration.
        
        Args:
            workspace_dir: Arbeitsverzeichnis für Experimente
        """
        self.workspace_dir = Path(workspace_dir)
        self.kilo_command = "kilo"
        self.timeout = 300  # 5 Minuten Standard-Timeout
        
    def execute_kilo_command(
        self,
        command: str = "kilo",
        parameters: Optional[List[str]] = None,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Führt einen Kilo-CMD-Befehl aus.
        
        Args:
            command: Der Kilo-Befehl (Standard: "kilo")
            parameters: Liste der Parameter für den Befehl
            timeout: Timeout in Sekunden (optional)
            
        Returns:
            Dict mit 'success', 'stdout', 'stderr', 'return_code'
        """
        if parameters is None:
            parameters = []
        
        if timeout is None:
            timeout = self.timeout
        
        # Befehl zusammenbauen
        cmd_list = [command] + parameters
        
        logger.info(f"Führe Kilo-Befehl aus: {' '.join(cmd_list)}")
        
        try:
            # Befehl ausführen
            result = subprocess.run(
                cmd_list,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.workspace_dir
            )
            
            response = {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
                "command": " ".join(cmd_list)
            }
            
            if response["success"]:
                logger.info(f"Kilo-Befehl erfolgreich: {response['command']}")
            else:
                logger.warning(f"Kilo-Befehl fehlgeschlagen: {response['command']}")
                logger.warning(f"stderr: {response['stderr']}")
            
            return response
            
        except subprocess.TimeoutExpired:
            logger.error(f"Kilo-Befehl Timeout nach {timeout} Sekunden")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Befehl Timeout nach {timeout} Sekunden",
                "return_code": -1,
                "command": " ".join(cmd_list)
            }
        except FileNotFoundError:
            logger.error(f"Befehl '{command}' nicht gefunden")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Befehl '{command}' nicht gefunden. Stellen Sie sicher, dass Kilo installiert ist.",
                "return_code": -1,
                "command": " ".join(cmd_list)
            }
        except Exception as e:
            logger.error(f"Unerwarteter Fehler bei Kilo-Befehl: {str(e)}")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Unerwarteter Fehler: {str(e)}",
                "return_code": -1,
                "command": " ".join(cmd_list)
            }
    
    def execute_kilo_with_config(
        self,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Führt Kilo mit einer Konfiguration aus.
        
        Args:
            config: Konfigurations-Dictionary mit 'command' und 'parameters'
            
        Returns:
            Ergebnis des Kilo-Befehls
        """
        command = config.get("command", "kilo")
        parameters = config.get("parameters", [])
        timeout = config.get("timeout", self.timeout)
        
        return self.execute_kilo_command(
            command=command,
            parameters=parameters,
            timeout=timeout
        )
    
    def save_kilo_result(
        self,
        result: Dict[str, Any],
        filename: str = "kilo_result.json"
    ):
        """
        Speichert das Ergebnis eines Kilo-Befehls in einer Datei.
        
        Args:
            result: Ergebnis des Kilo-Befehls
            filename: Dateiname für das Ergebnis
        """
        result_path = self.workspace_dir / filename
        
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Kilo-Ergebnis gespeichert in: {result_path}")
    
    def load_kilo_config(
        self,
        config_path: str = "kilo_config.json"
    ) -> Optional[Dict[str, Any]]:
        """
        Lädt eine Kilo-Konfiguration aus einer Datei.
        
        Args:
            config_path: Pfad zur Konfigurationsdatei
            
        Returns:
            Konfigurations-Dictionary oder None
        """
        config_file = self.workspace_dir / config_path
        
        if not config_file.exists():
            logger.warning(f"Kilo-Konfiguration nicht gefunden: {config_file}")
            return None
        
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            logger.info(f"Kilo-Konfiguration geladen: {config_file}")
            return config
            
        except Exception as e:
            logger.error(f"Fehler beim Laden der Kilo-Konfiguration: {str(e)}")
            return None
    
    def get_kilo_help(self) -> Dict[str, Any]:
        """
        Ruft die Hilfe für Kilo ab.
        
        Returns:
            Ergebnis des Kilo-Hilfe-Befehls
        """
        return self.execute_kilo_command(
            command="kilo",
            parameters=["--help"]
        )
    
    def get_kilo_version(self) -> Dict[str, Any]:
        """
        Ruft die Version von Kilo ab.
        
        Returns:
            Ergebnis des Kilo-Versions-Befehls
        """
        return self.execute_kilo_command(
            command="kilo",
            parameters=["--version"]
        )


def create_kilo_integration(workspace_dir: str) -> KiloAgentIntegration:
    """
    Factory-Funktion zum Erstellen einer Kilo-Agent-Integration.
    
    Args:
        workspace_dir: Arbeitsverzeichnis für Experimente
        
    Returns:
        KiloAgentIntegration Instanz
    """
    return KiloAgentIntegration(Path(workspace_dir))


# Beispiel für die Verwendung im AI-Scientist-Kontext
if __name__ == "__main__":
    # Beispiel-Verwendung
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        integration = create_kilo_integration(tmpdir)
        
        # Hilfe abrufen
        help_result = integration.get_kilo_help()
        print("Kilo-Hilfe:")
        print(json.dumps(help_result, indent=2, ensure_ascii=False))
        
        # Version abrufen
        version_result = integration.get_kilo_version()
        print("\nKilo-Version:")
        print(json.dumps(version_result, indent=2, ensure_ascii=False))
