/**
 * IPC Handlers for File System Operations
 *
 * Provides direct access to enterprise_output folder for:
 * - Listing projects
 * - Loading project data (journal.json)
 * - Loading diagrams (.mmd files)
 * - File dialogs
 */

import { ipcMain, dialog } from 'electron';
import { readdir, readFile, stat, access } from 'fs/promises';
import { constants } from 'fs';
import { join } from 'path';

// Default enterprise_output location (relative to CWD)
let ENTERPRISE_OUTPUT = join(process.cwd(), 'enterprise_output');

export function registerFileSystemHandlers() {
  // Set custom enterprise_output path
  ipcMain.handle('config:setEnterpriseOutputPath', async (_, path: string) => {
    try {
      await access(path, constants.R_OK);
      ENTERPRISE_OUTPUT = path;
      return { success: true, data: path };
    } catch {
      return { success: false, error: `Cannot access path: ${path}` };
    }
  });

  // Get current enterprise_output path
  ipcMain.handle('config:getEnterpriseOutputPath', async () => {
    return { success: true, data: ENTERPRISE_OUTPUT };
  });

  // List all projects in enterprise_output
  ipcMain.handle('projects:list', async () => {
    try {
      // Check if directory exists
      try {
        await access(ENTERPRISE_OUTPUT, constants.R_OK);
      } catch {
        return {
          success: false,
          error: `enterprise_output folder not found at: ${ENTERPRISE_OUTPUT}`
        };
      }

      const entries = await readdir(ENTERPRISE_OUTPUT, { withFileTypes: true });

      const projects = await Promise.all(
        entries
          .filter(e => e.isDirectory())
          .map(async (dir) => {
            const projectPath = join(ENTERPRISE_OUTPUT, dir.name);
            const diagramsPath = join(projectPath, 'diagrams');
            const journalPath = join(projectPath, 'journal.json');

            let diagramCount = 0;
            let nodeCount = 0;

            // Count diagrams
            try {
              const diagrams = await readdir(diagramsPath);
              diagramCount = diagrams.filter(f => f.endsWith('.mmd')).length;
            } catch {
              // No diagrams folder
            }

            // Count nodes from journal.json
            try {
              const journalContent = await readFile(journalPath, 'utf-8');
              const journal = JSON.parse(journalContent);
              nodeCount = Object.keys(journal.nodes || {}).length;
            } catch {
              // No journal.json or parse error
            }

            const stats = await stat(projectPath);

            return {
              name: dir.name,
              path: projectPath,
              diagramCount,
              nodeCount,
              lastModified: stats.mtime
            };
          })
      );

      // Sort by last modified (newest first)
      projects.sort((a, b) =>
        new Date(b.lastModified).getTime() - new Date(a.lastModified).getTime()
      );

      return { success: true, data: projects };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : String(error)
      };
    }
  });

  // Load project data from journal.json
  ipcMain.handle('projects:load', async (_, projectName: string) => {
    try {
      const journalPath = join(ENTERPRISE_OUTPUT, projectName, 'journal.json');
      const content = await readFile(journalPath, 'utf-8');
      const data = JSON.parse(content);
      return { success: true, data };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : String(error)
      };
    }
  });

  // List all diagrams for a project
  ipcMain.handle('diagrams:list', async (_, projectName: string) => {
    try {
      const diagramsPath = join(ENTERPRISE_OUTPUT, projectName, 'diagrams');
      const files = await readdir(diagramsPath);

      const diagrams = await Promise.all(
        files
          .filter(f => f.endsWith('.mmd'))
          .map(async (filename) => {
            const filePath = join(diagramsPath, filename);
            const code = await readFile(filePath, 'utf-8');

            // Parse filename: REQ-001_flowchart.mmd
            const match = filename.match(/^([A-Z]+-\d+)_(\w+)\.mmd$/);

            return {
              filename,
              reqId: match?.[1] || filename.replace('.mmd', ''),
              type: match?.[2] || 'unknown',
              code
            };
          })
      );

      // Sort by reqId then type
      diagrams.sort((a, b) => {
        const reqCompare = a.reqId.localeCompare(b.reqId);
        if (reqCompare !== 0) return reqCompare;
        return a.type.localeCompare(b.type);
      });

      return { success: true, data: diagrams };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : String(error)
      };
    }
  });

  // Load single diagram content
  ipcMain.handle('diagrams:load', async (_, projectName: string, filename: string) => {
    try {
      const filePath = join(ENTERPRISE_OUTPUT, projectName, 'diagrams', filename);
      const code = await readFile(filePath, 'utf-8');
      return { success: true, data: code };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : String(error)
      };
    }
  });

  // Select folder dialog
  ipcMain.handle('dialog:selectFolder', async () => {
    const result = await dialog.showOpenDialog({
      properties: ['openDirectory'],
      title: 'Enterprise Output Ordner wählen'
    });
    return result.filePaths[0];
  });

  // Select file dialog
  ipcMain.handle('dialog:selectFile', async (_, filters?: { name: string; extensions: string[] }[]) => {
    const result = await dialog.showOpenDialog({
      properties: ['openFile'],
      filters: filters || [
        { name: 'JSON Files', extensions: ['json'] },
        { name: 'All Files', extensions: ['*'] }
      ]
    });
    return result.filePaths[0];
  });

  console.log('[IPC] File system handlers registered');
}
