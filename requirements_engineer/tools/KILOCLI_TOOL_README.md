# Kilocode CLI Tool - Python Wrapper

Ein Python-Wrapper für die Kilocode CLI, der es Agenten ermöglicht, Kilocode-Befehle über die Kommandozeile auszuführen.

## Installation

### Voraussetzungen

1. **Node.js und npm** müssen installiert sein
2. **Kilocode CLI** muss global installiert sein:

```bash
npm install -g @kilocode/cli
```

### Installation des Python-Tools

Das Tool ist bereits im Projekt enthalten unter:
```
ai_scientist/tools/kilocli_tool.py
```

## Verwendung

### Grundlegende Verwendung

```python
from ai_scientist.tools.kilocli_tool import KilocodeCliTool, run_kilocode

# Tool initialisieren
tool = KilocodeCliTool()

# Einen autonomen Befehl ausführen
result = tool.run_autonomous(
    prompt="Erstelle eine einfache Python-Funktion",
    mode="code",
    workspace="c:/path/to/workspace"
)

print(result["stdout"])
```

### Convenience-Funktionen

```python
from ai_scientist.tools.kilocli_tool import run_kilocode, list_kilocode_models, get_kilocode_version

# Kilocode-Befehl ausführen
result = run_kilocode(
    prompt="Analysiere den Code",
    mode="ask",
    workspace="c:/path/to/workspace"
)

# Verfügbare Modelle auflisten
models = list_kilocode_models()
print(models)

# Version abrufen
version = get_kilocode_version()
print(version)
```

## API-Referenz

### KilocodeCliTool Klasse

#### `__init__(kilocode_path: Optional[str] = None)`

Initialisiert das Tool. Wenn `kilocode_path` nicht angegeben wird, wird der Pfad automatisch gesucht.

#### `run_autonomous(...)`

Führt einen autonomen Kilocode-Befehl aus.

**Parameter:**
- `prompt` (str): Der Prompt oder Befehl, der ausgeführt werden soll
- `workspace` (Optional[str]): Pfad zum Workspace-Verzeichnis
- `mode` (Optional[str]): Modus (architect, code, ask, debug, orchestrator, review)
- `model` (Optional[str]): Modell-Override für den ausgewählten Provider
- `provider` (Optional[str]): Provider-ID (z.B. 'kilocode-1')
- `timeout` (Optional[int]): Timeout in Sekunden
- `json_output` (bool): Ob die Ausgabe als JSON erfolgen soll
- `yolo` (bool): Auto-approve aller Tool-Permissions
- `continue_session` (bool): Ob die letzte Sitzung fortgesetzt werden soll
- `parallel` (bool): Ob im Parallel-Modus ausgeführt werden soll
- `existing_branch` (Optional[str]): Existierender Branch für Parallel-Modus
- `session_id` (Optional[str]): Session-ID zum Wiederherstellen
- `attach_files` (Optional[List[str]]): Liste der Dateien, die angehängt werden sollen
- `append_system_prompt` (Optional[str]): Zusätzliche System-Prompts
- `on_task_completed` (Optional[str]): Prompt nach Aufgabenabschluss

**Rückgabe:** Dictionary mit `stdout`, `stderr`, `returncode`, `success`

#### `list_models(provider: Optional[str] = None)`

Listet verfügbare Modelle auf.

**Parameter:**
- `provider` (Optional[str]): Optionaler Provider-Filter

**Rückgabe:** Dictionary mit den Modellen als JSON

#### `open_config()`

Öffnet die Konfigurationsdatei im Standard-Editor.

**Rückgabe:** Dictionary mit dem Ergebnis

#### `run_debug(mode: Optional[str] = None)`

Führt einen System-Kompatibilitätscheck durch.

**Parameter:**
- `mode` (Optional[str]): Optionaler Debug-Modus

**Rückgabe:** Dictionary mit dem Ergebnis

#### `get_version()`

Gibt die Version von Kilocode CLI zurück.

**Rückgabe:** Dictionary mit der Version

#### `restore_session(session_id: str)`

Stellt eine Sitzung anhand der ID wieder her.

**Parameter:**
- `session_id` (str): Die Session-ID

**Rückgabe:** Dictionary mit dem Ergebnis

#### `fork_session(share_id: str)`

Forkt eine Sitzung anhand der Share-ID.

**Parameter:**
- `share_id` (str): Die Share-ID

**Rückgabe:** Dictionary mit dem Ergebnis

## CLI-Optionen vs. Interaktive Befehle

### CLI-Optionen (für Automatisierung)

Diese Optionen können über die Python-API verwendet werden:

| Option | Beschreibung |
|--------|-------------|
| `-m, --mode <mode>` | Modus setzen (architect, code, ask, debug, orchestrator, review) |
| `-w, --workspace <path>` | Workspace-Pfad |
| `-a, --auto` | Autonomer Modus (nicht interaktiv) |
| `--yolo` | Auto-approve aller Tool-Permissions (erfordert --auto) |
| `-j, --json` | JSON-Ausgabe (erfordert --auto, wird automatisch hinzugefügt) |
| `-i, --json-io` | Bidirektionaler JSON-Modus |
| `-c, --continue` | Letzte Sitzung fortsetzen |
| `-t, --timeout <seconds>` | Timeout für autonomen Modus |
| `-p, --parallel` | Parallel-Modus |
| `-e, --existing-branch <branch>` | Existierender Branch (Parallel-Modus) |
| `-P, --provider <id>` | Provider auswählen |
| `-M, --model <model>` | Modell-Override |
| `-s, --session <sessionId>` | Sitzung wiederherstellen |
| `-f, --fork <shareId>` | Sitzung forken |
| `--nosplash` | Willkommensnachricht deaktivieren |
| `--append-system-prompt <text>` | Zusätzliche System-Prompts |
| `--append-system-prompt-file <path>` | System-Prompts aus Datei lesen |
| `--on-task-completed <prompt>` | Prompt nach Aufgabenabschluss |
| `--attach <path>` | Datei anhängen |

**Wichtig:** Die Optionen `--json` und `--yolo` erfordern die `--auto`-Flag. Das Tool fügt diese automatisch hinzu, wenn diese Optionen verwendet werden.

**Autonome Ausführung:** Die `--yolo`-Option ist standardmäßig auf `True` gesetzt, um alle Tool-Permissions automatisch zu genehmigen. Dies ermöglicht eine vollständig autonome Ausführung ohne Benutzerinteraktion.

### CLI-Befehle

| Befehl | Beschreibung |
|--------|-------------|
| `auth` | Authentifizierung verwalten |
| `config` | Konfigurationsdatei öffnen |
| `debug [mode]` | System-Kompatibilitätscheck |
| `models [options]` | Verfügbare Modelle auflisten |

### Interaktive TUI-Befehle (nicht über CLI verfügbar)

Diese Befehle werden **innerhalb** der interaktiven Kilocode-TUI-Sitzung verwendet und können **nicht** direkt über die CLI aufgerufen werden:

| Befehl | Beschreibung |
|--------|-------------|
| `/mode` | Zwischen Modi wechseln |
| `/model` | Verfügbare Modelle anzeigen und wechseln |
| `/model list` | Verfügbare Modelle auflisten |
| `/model info <name>` | Beschreibung für ein Modell anzeigen |
| `/model select` | Neues Modell auswählen |
| `/checkpoint list` | Alle Checkpoints auflisten |
| `/checkpoint restore <id>` | Zu einem Checkpoint zurückkehren |
| `/tasks` | Aufgaben-Historie anzeigen |
| `/tasks search <query>` | Aufgaben durchsuchen |
| `/tasks select <id>` | Zu einer Aufgabe wechseln |
| `/tasks page <n>`` | Zu einer Seite gehen |
| `/tasks next` | Zur nächsten Seite |
| `/tasks prev` | Zur vorherigen Seite |
| `/tasks sort <order>`` | Sortierreihenfolge ändern |
| `/tasks filter <filter>`` | Aufgaben filtern |
| `/teams` | Organisationen auflisten |
| `/teams select` | Organisation wechseln |
| `/config` | Konfigurationseditor öffnen |
| `/new` | Neue Aufgabe starten |
| `/help` | Verfügbare Befehle auflisten |
| `/exit` | CLI beenden |

**Wichtig:** Für die Automatisierung mit Agenten sollten die CLI-Optionen verwendet werden, nicht die interaktiven TUI-Befehle.

## Beispiele

### Beispiel 1: Einfacher Befehl

```python
from ai_scientist.tools.kilocli_tool import run_kilocode

result = run_kilocode(
    prompt="Erstelle eine Hello World Funktion in Python",
    mode="code",
    workspace="c:/Users/User/Desktop/Sakana-ai-research/AI-Scientist-v2"
)

if result["success"]:
    print("Erfolg:", result["stdout"])
else:
    print("Fehler:", result["stderr"])
```

### Beispiel 2: Mit Timeout und JSON-Ausgabe

```python
from ai_scientist.tools.kilocli_tool import KilocodeCliTool

tool = KilocodeCliTool()

result = tool.run_autonomous(
    prompt="Analysiere die Projektstruktur",
    mode="ask",
    workspace="c:/Users/User/Desktop/Sakana-ai-research/AI-Scientist-v2",
    timeout=300,
    json_output=True
)

print(json.dumps(result, indent=2))
```

### Beispiel 3: Mit Dateianhang

```python
from ai_scientist.tools.kilocli_tool import KilocodeCliTool

tool = KilocodeCliTool()

result = tool.run_autonomous(
    prompt="Analysiere das angehängte Bild",
    mode="ask",
    workspace="c:/Users/User/Desktop/Sakana-ai-research/AI-Scientist-v2",
    attach_files=["c:/path/to/image.png"]
)

print(result["stdout"])
```

### Beispiel 4: Modelle auflisten

```python
from ai_scientist.tools.kilocli_tool import list_kilocode_models

models = list_kilocode_models()

if models["success"]:
    for model in models["models"]:
        print(f"- {model['name']}: {model['description']}")
else:
    print("Fehler:", models["error"])
```

### Beispiel 5: Sitzung wiederherstellen

```python
from ai_scientist.tools.kilocli_tool import KilocodeCliTool

tool = KilocodeCliTool()

result = tool.restore_session("abc123")

if result["success"]:
    print("Sitzung wiederhergestellt")
else:
    print("Fehler:", result["stderr"])
```

## Fehlerbehandlung

```python
from ai_scientist.tools.kilocli_tool import KilocodeCliTool, FileNotFoundError

try:
    tool = KilocodeCliTool()
    result = tool.run_autonomous("Test prompt", mode="code")
    
    if result["success"]:
        print("Erfolg:", result["stdout"])
    else:
        print("Befehl fehlgeschlagen:", result["stderr"])
        
except FileNotFoundError as e:
    print("Kilocode CLI nicht gefunden:", e)
except TimeoutError as e:
    print("Timeout:", e)
```

## Integration in user_kilo_agent.py

Das Tool kann in [`user_kilo_agent.py`](../user_kilo_agent.py) wie folgt verwendet werden:

```python
from ai_scientist.tools.kilocli_tool import KilocodeCliTool

# Tool initialisieren
kilocode_tool = KilocodeCliTool()

# Kilocode-Befehl ausführen
result = kilocode_tool.run_autonomous(
    prompt=user_prompt,
    mode="code",
    workspace=workspace_path
)
```

## Lizenz

Dieses Tool ist Teil des AI-Scientist-v2 Projekts.
