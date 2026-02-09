"""
Test-Skript für Kilo CMD Tool
"""

import sys
import os
import json
from pathlib import Path

# Kodierung auf UTF-8 setzen für Windows-Kompatibilität
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Pfad zum Projektverzeichnis hinzufügen
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

from ai_scientist.tools.kilo_cmd_tool import KiloCmdTool

def test_kilo_tool():
    """Testet das Kilo CMD Tool."""
    print("=" * 60)
    print("Teste Kilo CMD Tool")
    print("=" * 60)
    
    # Tool erstellen
    tool = KiloCmdTool()
    
    # Test 1: Einfacher Befehl
    print("\nTest 1: Einfacher Befehl (python --version)")
    print("-" * 60)
    result = tool.use_tool(command="python", parameters=["--version"])
    print(f"Success: {result['success']}")
    print(f"Return Code: {result['return_code']}")
    print(f"Stdout: {result['stdout']}")
    print(f"Stderr: {result['stderr']}")
    print(f"Command: {result['command']}")
    
    # Test 2: Befehl mit strukturiertem Output
    print("\nTest 2: Befehl mit strukturiertem Output (echo 'Hallo Welt')")
    print("-" * 60)
    result = tool.use_tool(command="echo", parameters=["Hallo Welt"], structured_output=True)
    print(f"Success: {result['success']}")
    print(f"Return Code: {result['return_code']}")
    print(f"Stdout: {result['stdout']}")
    print(f"Stderr: {result['stderr']}")
    print(f"Command: {result['command']}")
    print(f"Structured: {result.get('structured', False)}")
    
    # Test 3: Nicht existierender Befehl
    print("\nTest 3: Nicht existierender Befehl (nicht_existierender_befehl)")
    print("-" * 60)
    result = tool.use_tool(command="nicht_existierender_befehl", parameters=[])
    print(f"Success: {result['success']}")
    print(f"Return Code: {result['return_code']}")
    print(f"Stdout: {result['stdout']}")
    print(f"Stderr: {result['stderr']}")
    print(f"Command: {result['command']}")
    
    # Test 4: Kilo Befehl (falls installiert)
    print("\nTest 4: Kilo Befehl (kilo --help)")
    print("-" * 60)
    result = tool.use_tool(command="kilo", parameters=["--help"])
    print(f"Success: {result['success']}")
    print(f"Return Code: {result['return_code']}")
    print(f"Stdout: {result['stdout'][:200] if result['stdout'] else ''}...")
    print(f"Stderr: {result['stderr'][:200] if result['stderr'] else ''}...")
    print(f"Command: {result['command']}")
    
    # Test 5: AutoGen Tool Konvertierung
    print("\nTest 5: AutoGen Tool Konvertierung")
    print("-" * 60)
    autogen_tool = tool.to_autogen_tool()
    print(f"Tool Name: {autogen_tool.name}")
    print(f"Tool Description: {autogen_tool.description}")
    print(f"Tool Schema: {json.dumps(autogen_tool.schema, indent=2)}")
    
    print("\n" + "=" * 60)
    print("Test abgeschlossen")
    print("=" * 60)

if __name__ == "__main__":
    test_kilo_tool()
