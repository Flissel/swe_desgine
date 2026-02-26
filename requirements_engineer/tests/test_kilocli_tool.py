"""
Unit-Tests für das Kilocode CLI Tool

Diese Tests überprüfen die Funktionalität des KilocodeCliTool.
"""

import unittest
import json
import os
from unittest.mock import Mock, patch, MagicMock
from requirements_engineer.tools.kilocli_tool import KilocodeCliTool, run_kilocode, list_kilocode_models, get_kilocode_version


class TestKilocodeCliTool(unittest.TestCase):
    """Test-Klasse für KilocodeCliTool"""
    
    def setUp(self):
        """Wird vor jedem Test ausgeführt"""
        # Mock für subprocess.run erstellen
        self.mock_subprocess_run = patch('requirements_engineer.tools.kilocli_tool.subprocess.run')
        self.mock_run = self.mock_subprocess_run.start()
        
        # Mock für os.path.exists erstellen
        self.mock_path_exists = patch('requirements_engineer.tools.kilocli_tool.os.path.exists')
        self.mock_exists = self.mock_path_exists.start()
        self.mock_exists.return_value = True
        
        # Mock für subprocess.where erstellen
        self.mock_where = patch('requirements_engineer.tools.kilocli_tool.subprocess.run')
        self.mock_where_run = self.mock_where.start()
        
    def tearDown(self):
        """Wird nach jedem Test ausgeführt"""
        self.mock_subprocess_run.stop()
        self.mock_path_exists.stop()
        self.mock_where.stop()
    
    def test_init_with_path(self):
        """Testet die Initialisierung mit einem Pfad"""
        tool = KilocodeCliTool(kilocode_path="C:/path/to/kilocode.cmd")
        self.assertEqual(tool.kilocode_path, "C:/path/to/kilocode.cmd")
    
    def test_init_without_path(self):
        """Testet die Initialisierung ohne Pfad"""
        # Mock für where-Befehl
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "C:/path/to/kilocode.cmd\n"
        self.mock_where_run.return_value = mock_result
        
        tool = KilocodeCliTool()
        self.assertIsNotNone(tool.kilocode_path)
    
    def test_init_file_not_found(self):
        """Testet die Initialisierung, wenn die Datei nicht gefunden wird"""
        self.mock_exists.return_value = False
        
        with self.assertRaises(FileNotFoundError):
            KilocodeCliTool(kilocode_path="C:/nonexistent/kilocode.cmd")
    
    def test_run_command_success(self):
        """Testet das Ausführen eines Befehls bei Erfolg"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Erfolgreich ausgeführt"
        mock_result.stderr = ""
        self.mock_run.return_value = mock_result
        
        tool = KilocodeCliTool(kilocode_path="C:/path/to/kilocode.cmd")
        result = tool._run_command(["--help"])
        
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "Erfolgreich ausgeführt")
    
    def test_run_command_failure(self):
        """Testet das Ausführen eines Befehls bei Fehler"""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Fehler aufgetreten"
        self.mock_run.return_value = mock_result
        
        tool = KilocodeCliTool(kilocode_path="C:/path/to/kilocode.cmd")
        result = tool._run_command(["--invalid"])
        
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "Fehler aufgetreten")
    
    def test_run_command_timeout(self):
        """Testet das Ausführen eines Befehls mit Timeout"""
        from subprocess import TimeoutExpired
        
        self.mock_run.side_effect = TimeoutExpired("kilocode.cmd", 60)
        
        tool = KilocodeCliTool(kilocode_path="C:/path/to/kilocode.cmd")
        
        with self.assertRaises(TimeoutError):
            tool._run_command(["--help"], timeout=60)
    
    def test_run_autonomous_basic(self):
        """Testet das Ausführen eines autonomen Befehls"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Ergebnis"
        mock_result.stderr = ""
        self.mock_run.return_value = mock_result
        
        tool = KilocodeCliTool(kilocode_path="C:/path/to/kilocode.cmd")
        result = tool.run_autonomous("Test prompt")
        
        self.assertTrue(result["success"])
        self.assertEqual(result["stdout"], "Ergebnis")
    
    def test_run_autonomous_with_mode(self):
        """Testet das Ausführen eines autonomen Befehls mit Modus"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Ergebnis"
        mock_result.stderr = ""
        self.mock_run.return_value = mock_result
        
        tool = KilocodeCliTool(kilocode_path="C:/path/to/kilocode.cmd")
        result = tool.run_autonomous("Test prompt", mode="code")
        
        self.assertTrue(result["success"])
        # Prüfen, ob der Modus-Parameter übergeben wurde
        call_args = self.mock_run.call_args[0][0]
        self.assertIn("-m", call_args)
        self.assertIn("code", call_args)
    
    def test_run_autonomous_with_workspace(self):
        """Testet das Ausführen eines autonomen Befehls mit Workspace"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Ergebnis"
        mock_result.stderr = ""
        self.mock_run.return_value = mock_result
        
        tool = KilocodeCliTool(kilocode_path="C:/path/to/kilocode.cmd")
        result = tool.run_autonomous("Test prompt", workspace="C:/workspace")
        
        self.assertTrue(result["success"])
        # Prüfen, ob der Workspace-Parameter übergeben wurde
        call_args = self.mock_run.call_args[0][0]
        self.assertIn("-w", call_args)
        self.assertIn("C:/workspace", call_args)
    
    def test_run_autonomous_with_timeout(self):
        """Testet das Ausführen eines autonomen Befehls mit Timeout"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Ergebnis"
        mock_result.stderr = ""
        self.mock_run.return_value = mock_result
        
        tool = KilocodeCliTool(kilocode_path="C:/path/to/kilocode.cmd")
        result = tool.run_autonomous("Test prompt", timeout=60)
        
        self.assertTrue(result["success"])
        # Prüfen, ob der Timeout-Parameter übergeben wurde
        call_args = self.mock_run.call_args[0][0]
        self.assertIn("-t", call_args)
        self.assertIn("60", call_args)
    
    def test_run_autonomous_with_json_output(self):
        """Testet das Ausführen eines autonomen Befehls mit JSON-Ausgabe"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = '{"result": "success"}'
        mock_result.stderr = ""
        self.mock_run.return_value = mock_result
        
        tool = KilocodeCliTool(kilocode_path="C:/path/to/kilocode.cmd")
        result = tool.run_autonomous("Test prompt", json_output=True)
        
        self.assertTrue(result["success"])
        # Prüfen, ob der JSON-Parameter übergeben wurde
        call_args = self.mock_run.call_args[0][0]
        self.assertIn("-j", call_args)
    
    def test_list_models_success(self):
        """Testet das Auflisten der Modelle bei Erfolg"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([
            {"name": "model1", "description": "Model 1"},
            {"name": "model2", "description": "Model 2"}
        ])
        mock_result.stderr = ""
        self.mock_run.return_value = mock_result
        
        tool = KilocodeCliTool(kilocode_path="C:/path/to/kilocode.cmd")
        result = tool.list_models()
        
        self.assertTrue(result["success"])
        self.assertEqual(len(result["models"]), 2)
    
    def test_list_models_with_provider(self):
        """Testet das Auflisten der Modelle mit Provider-Filter"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([
            {"name": "model1", "description": "Model 1"}
        ])
        mock_result.stderr = ""
        self.mock_run.return_value = mock_result
        
        tool = KilocodeCliTool(kilocode_path="C:/path/to/kilocode.cmd")
        result = tool.list_models(provider="kilocode-1")
        
        self.assertTrue(result["success"])
        # Prüfen, ob der Provider-Parameter übergeben wurde
        call_args = self.mock_run.call_args[0][0]
        self.assertIn("-P", call_args)
        self.assertIn("kilocode-1", call_args)
    
    def test_list_models_invalid_json(self):
        """Testet das Auflisten der Modelle mit ungültigem JSON"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Kein gültiges JSON"
        mock_result.stderr = ""
        self.mock_run.return_value = mock_result
        
        tool = KilocodeCliTool(kilocode_path="C:/path/to/kilocode.cmd")
        result = tool.list_models()
        
        self.assertFalse(result["success"])
        self.assertIn("Konnte Modelle nicht als JSON parsen", result["error"])
    
    def test_get_version(self):
        """Testet das Abrufen der Version"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "0.26.1"
        mock_result.stderr = ""
        self.mock_run.return_value = mock_result
        
        tool = KilocodeCliTool(kilocode_path="C:/path/to/kilocode.cmd")
        result = tool.get_version()
        
        self.assertTrue(result["success"])
        self.assertEqual(result["version"], "0.26.1")
    
    def test_restore_session(self):
        """Testet das Wiederherstellen einer Sitzung"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Sitzung wiederhergestellt"
        mock_result.stderr = ""
        self.mock_run.return_value = mock_result
        
        tool = KilocodeCliTool(kilocode_path="C:/path/to/kilocode.cmd")
        result = tool.restore_session("abc123")
        
        self.assertTrue(result["success"])
        # Prüfen, ob die Session-ID übergeben wurde
        call_args = self.mock_run.call_args[0][0]
        self.assertIn("-s", call_args)
        self.assertIn("abc123", call_args)
    
    def test_fork_session(self):
        """Testet das Forken einer Sitzung"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Sitzung geforkt"
        mock_result.stderr = ""
        self.mock_run.return_value = mock_result
        
        tool = KilocodeCliTool(kilocode_path="C:/path/to/kilocode.cmd")
        result = tool.fork_session("share123")
        
        self.assertTrue(result["success"])
        # Prüfen, ob die Share-ID übergeben wurde
        call_args = self.mock_run.call_args[0][0]
        self.assertIn("-f", call_args)
        self.assertIn("share123", call_args)


class TestConvenienceFunctions(unittest.TestCase):
    """Test-Klasse für Convenience-Funktionen"""
    
    def setUp(self):
        """Wird vor jedem Test ausgeführt"""
        self.mock_tool_class = patch('requirements_engineer.tools.kilocli_tool.KilocodeCliTool')
        self.mock_tool = self.mock_tool_class.start()
        
        self.mock_instance = Mock()
        self.mock_tool.return_value = self.mock_instance
    
    def tearDown(self):
        """Wird nach jedem Test ausgeführt"""
        self.mock_tool_class.stop()
    
    def test_run_kilocode(self):
        """Testet die Convenience-Funktion run_kilocode"""
        self.mock_instance.run_autonomous.return_value = {
            "success": True,
            "stdout": "Ergebnis",
            "stderr": "",
            "returncode": 0
        }
        
        result = run_kilocode("Test prompt", mode="code")
        
        self.assertTrue(result["success"])
        self.mock_instance.run_autonomous.assert_called_once()
    
    def test_list_kilocode_models(self):
        """Testet die Convenience-Funktion list_kilocode_models"""
        self.mock_instance.list_models.return_value = {
            "success": True,
            "models": [{"name": "model1"}]
        }
        
        result = list_kilocode_models()
        
        self.assertTrue(result["success"])
        self.mock_instance.list_models.assert_called_once()
    
    def test_get_kilocode_version(self):
        """Testet die Convenience-Funktion get_kilocode_version"""
        self.mock_instance.get_version.return_value = {
            "success": True,
            "version": "0.26.1"
        }
        
        result = get_kilocode_version()
        
        self.assertTrue(result["success"])
        self.assertEqual(result["version"], "0.26.1")
        self.mock_instance.get_version.assert_called_once()


if __name__ == "__main__":
    unittest.main()
