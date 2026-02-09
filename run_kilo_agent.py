"""
Kilo Agent - Standalone Version

Dieses Skript erstellt einen standalone AutoGen 0.4 Agent mit Kilo-CMD Tool.
"""

import asyncio
import argparse
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models import OpenAIChatCompletionClient
from ai_scientist.tools.kilo_cmd_tool import KiloCmdTool


async def create_kilo_agent(
    model_name: str = "gpt-4o-mini",
    api_key: str = None,
    base_url: str = None
    timeout: int = 300
) -> AssistantAgent:
    """
    Erstellt einen AutoGen 0.4 Agent mit Kilo-CMD Tool.
    
    Args:
        model_name: Name des zu verwendenden Modells
        api_key: API Key für das Modell
        base_url: Base URL für die API (optional)
        timeout: Timeout in Sekunden für Kilo-Befehle
        
    Returns:
        Konfigurierter AssistantAgent
    """
    # Model Client erstellen
    model_client = OpenAIChatCompletionClient(
        model=model_name,
        api_key=api_key,
        base_url=base_url
    )
    
    # Kilo-CMD Tool erstellen
    kilo_tool = KiloCmdTool()
    
    # Agent erstellen
    agent = AssistantAgent(
        name="kilo_agent",
        model_client=model_client,
        tools=[kilo_tool.to_autogen_tool()],
        system_message="""Du bist ein hilfreicher Assistent, der Kilo-CMD-Befehle ausführen kann.
Du hast Zugriff auf folgende Tools:
- kilo_cmd: Führt Kilo-CMD-Befehle mit Parametern aus
- kilo_help: Zeigt die Hilfe für Kilo an
- kilo_version: Zeigt die Version von Kilo an

Verwende diese Tools, um die Anfragen des Benutzers zu erfüllen."""
    )
    
    return agent


async def run_interactive_session(
    model_name: str = "gpt-4o-mini",
    api_key: str = None,
    base_url: str = None,
    timeout: int = 300
):
    """
    Führt eine interaktive Sitzung mit dem Kilo-Agenten durch.
    
    Args:
        model_name: Name des zu verwendenden Modells
        api_key: API Key für das Modell
        base_url: Base URL für die API (optional)
        timeout: Timeout in Sekunden für Kilo-Befehle
    """
    print("=== Kilo Agent - Interaktive Sitzung ===")
    print("Geben Sie 'exit' oder 'quit' ein, um die Sitzung zu beenden.\n")
    
    # Agent erstellen
    agent = await create_kilo_agent(
        model_name=model_name,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout
    )
    
    # Interaktive Schleife
    while True:
        try:
            # Benutzereingabe
            user_input = input("Sie: ").strip()
            
            if user_input.lower() in ['exit', 'quit', 'beenden']:
                print("Auf Wiedersehen!")
                break
            
            if not user_input:
                continue
            
            # Nachricht an den Agenten senden
            response = await agent.run(message=user_input)
            
            # Antwort anzeigen
            print(f"\nAgent: {response.message}\n")
            
        except KeyboardInterrupt:
            print("\nAuf Wiedersehen!")
        except Exception as e:
            print(f"\nFehler: {str(e)}\n")


async def run_single_task(
    task: str,
    model_name: str = "gpt-4o-mini",
    api_key: str = None,
    base_url: str = None,
    timeout: int = 300
):
    """
    Führt eine einzelne Aufgabe mit dem Kilo-Agenten durch.
    
    Args:
        task: Die Aufgabe, die ausgeführt werden soll
        model_name: Name des zu verwendenden Modells
        api_key: API Key für das Modell
        base_url: Base URL für die API (optional)
        timeout: Timeout in Sekunden für Kilo-Befehle
    """
    print(f"=== Kilo Agent - Aufgabe: {task} ===\n")
    
    # Agent erstellen
    agent = await create_kilo_agent(
        model_name=model_name,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout
    )
    
    # Aufgabe ausführen
    response = await agent.run(message=task)
    
    # Ergebnis anzeigen
    print(f"\nAgent-Antwort: {response.message}\n")


def main():
    """
    Hauptfunktion zum Ausführen des Kilo-Agenten.
    """
    parser = argparse.ArgumentParser(
        description="Kilo Agent - Standalone AutoGen 0.4 Agent mit Kilo-CMD Tool"
    )
    
    parser.add_argument(
        "--task",
        type=str,
        help="Einzelne Aufgabe, die ausgeführt werden soll"
    )
    
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o-mini",
        help="Name des zu verwendenden Modells (Standard: gpt-4o-mini)"
    )
    
    parser.add_argument(
        "--api-key",
        type=str,
        help="API Key für das Modell"
    )
    
    parser.add_argument(
        "--base-url",
        type=str,
        help="Base URL für die API (optional)"
    )
    
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout in Sekunden für Kilo-Befehle (Standard: 300)"
    )
    
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Startet eine interaktive Sitzung"
    )
    
    args = parser.parse_args()
    
    if args.interactive:
        asyncio.run(run_interactive_session(
            model_name=args.model,
            api_key=args.api_key,
            base_url=args.base_url,
            timeout=args.timeout
        ))
    elif args.task:
        asyncio.run(run_single_task(
            task=args.task,
            model_name=args.model,
            api_key=args.api_key,
            base_url=args.base_url,
            timeout=args.timeout
        ))
    else:
        # Standard: Interaktive Sitzung
        asyncio.run(run_interactive_session(
            model_name=args.model,
            api_key=args.api_key,
            base_url=args.base_url,
            timeout=args.timeout
        ))


if __name__ == "__main__":
    main()
