/**
 * App Store using Zustand
 *
 * Central state management with TypeScript for:
 * - Projects
 * - Nodes
 * - Connections
 * - UI State (selection, layout, etc.)
 */

import { create } from 'zustand';
import type {
  Project,
  ProjectData,
  CanvasNode,
  Connection,
  NodeData,
  LayoutMode,
  Diagram,
  DiagramType
} from '../types';

// Node type detection based on ID prefix or data fields
function detectNodeType(key: string, data: NodeData): CanvasNode['type'] {
  const reqId = data.requirement_id || data.id || key;

  if (reqId.startsWith('EPIC-')) return 'epic';
  if (reqId.startsWith('US-')) return 'user-story';
  if (reqId.startsWith('TEST-')) return 'test';
  if (reqId.startsWith('API-')) return 'api';
  if (reqId.startsWith('COMP-')) return 'component';
  if (reqId.startsWith('SCREEN-')) return 'screen';
  if (reqId.startsWith('PERSONA-')) return 'persona';
  if (reqId.startsWith('FLOW-')) return 'user-flow';
  if (reqId.startsWith('TASK-')) return 'task';
  if (reqId.startsWith('TECH-')) return 'tech-stack';
  if (key.includes('-diagram-') || key.includes('_diagram_')) return 'diagram';

  // Check for node type field
  if (data.type === 'epic') return 'epic';
  if (data.type === 'user-story') return 'user-story';

  // Default to requirement
  return 'requirement';
}

// Node size configuration (matching vanilla dashboard)
const NODE_SIZES: Record<string, { width: number; height: number }> = {
  'diagram': { width: 200, height: 160 },
  'test': { width: 180, height: 120 },
  'user-story': { width: 280, height: 150 },
  'requirement': { width: 320, height: 180 },
  'epic': { width: 350, height: 200 },
  'persona': { width: 250, height: 160 },
  'default': { width: 280, height: 160 }
};

// Column configuration for matrix layout
const COLUMN_ORDER = ['requirement', 'diagram', 'user-story', 'test', 'api', 'component'];

function getNodeSize(type: string) {
  return NODE_SIZES[type] || NODE_SIZES['default'];
}

// Convert NodeData from journal.json to CanvasNode
function nodeDataToCanvasNode(key: string, data: NodeData, index: number): CanvasNode {
  const nodeType = detectNodeType(key, data);
  const reqId = data.requirement_id || data.id || key;
  const size = getNodeSize(nodeType);

  // Initial position will be recalculated by layout
  const cols = 4;
  const row = Math.floor(index / cols);
  const col = index % cols;

  return {
    id: key,
    type: nodeType,
    data: {
      ...data,
      id: key,
      title: data.title || reqId
    },
    x: 100 + col * 400,
    y: 100 + row * 300,
    width: size.width,
    height: size.height
  };
}

// Valid diagram types
const VALID_DIAGRAM_TYPES: DiagramType[] = ['flowchart', 'sequence', 'class', 'er', 'state', 'c4'];

// Extract embedded mermaid diagrams as separate diagram nodes
function extractDiagramNodes(
  reqKey: string,
  reqData: NodeData,
  nodes: Record<string, CanvasNode>,
  connections: Connection[],
  startIndex: number
): number {
  const diagrams = reqData.mermaid_diagrams;
  if (!diagrams || typeof diagrams !== 'object') return startIndex;

  let index = startIndex;

  // Iterate over valid diagram types
  VALID_DIAGRAM_TYPES.forEach((diagramType) => {
    const code = diagrams[diagramType];
    if (!code || typeof code !== 'string') return;

    const diagramId = `${reqKey}-diagram-${diagramType}`;
    const size = getNodeSize('diagram');

    nodes[diagramId] = {
      id: diagramId,
      type: 'diagram',
      data: {
        id: diagramId,
        title: `${diagramType.charAt(0).toUpperCase() + diagramType.slice(1)} Diagram`,
        diagram_type: diagramType,
        mermaid_code: code,
        parent_requirement: reqKey
      },
      x: 0,
      y: 0,
      width: size.width,
      height: size.height
    };

    // Connect diagram to parent requirement
    connections.push({
      id: `${diagramId}-parent-${reqKey}`,
      from: diagramId,
      to: reqKey,
      type: 'parent'
    });

    index++;
  });

  return index;
}

/**
 * Matrix Layout Algorithm
 *
 * Organizes nodes in a grid where:
 * - Rows = Work packages (requirements grouped together)
 * - Columns = Node types (requirement, diagram, test, etc.)
 */
function applyMatrixLayout(
  nodes: Record<string, CanvasNode>,
  connections: Connection[]
): void {
  const baseX = 100;
  const baseY = 100;
  const padding = 40;
  const rowGap = 80;
  const colGap = 60;
  const rowHeaderWidth = 200;

  // Column widths by type
  const columnWidths: Record<string, number> = {
    'requirement': 360,
    'diagram': 240,
    'user-story': 300,
    'test': 200,
    'api': 200,
    'component': 200,
    'default': 280
  };

  // Detect work packages (group by parent requirement or by requirement itself)
  const workPackages = detectWorkPackages(nodes, connections);

  // Calculate column positions
  const columnX: Record<string, number> = {};
  let currentX = baseX + rowHeaderWidth;

  COLUMN_ORDER.forEach(col => {
    columnX[col] = currentX;
    currentX += (columnWidths[col] || columnWidths['default']) + colGap;
  });

  // Position nodes by work package (row) and type (column)
  let currentY = baseY;

  workPackages.forEach((wp) => {
    // Group nodes by type within this work package
    const nodesByType: Record<string, CanvasNode[]> = {};

    wp.nodeIds.forEach(nodeId => {
      const node = nodes[nodeId];
      if (!node) return;

      const type = node.type;
      if (!nodesByType[type]) nodesByType[type] = [];
      nodesByType[type].push(node);
    });

    // Calculate row height (max of all columns)
    let maxRowHeight = 200;
    Object.values(nodesByType).forEach(typeNodes => {
      const totalHeight = typeNodes.reduce((sum, n) => sum + n.height + padding, 0);
      maxRowHeight = Math.max(maxRowHeight, totalHeight);
    });

    // Position nodes in this row
    COLUMN_ORDER.forEach(colType => {
      const colNodes = nodesByType[colType] || [];
      let nodeY = currentY + padding;

      colNodes.forEach(node => {
        node.x = columnX[colType] || currentX;
        node.y = nodeY;
        nodeY += node.height + padding;
      });
    });

    currentY += maxRowHeight + rowGap;
  });

  console.log(`[MatrixLayout] Applied: ${workPackages.length} rows, ${Object.keys(nodes).length} nodes`);
}

/**
 * Detect work packages from nodes
 * Each requirement becomes a work package containing itself and its diagrams
 */
function detectWorkPackages(
  nodes: Record<string, CanvasNode>,
  _connections: Connection[]  // Reserved for future use
): Array<{ id: string; name: string; nodeIds: string[] }> {
  const packages: Array<{ id: string; name: string; nodeIds: string[] }> = [];

  // Find all requirements as package roots
  const requirements = Object.values(nodes).filter(n => n.type === 'requirement');

  requirements.forEach(req => {
    const packageNodes = [req.id];

    // Find all nodes connected to this requirement (diagrams, etc.)
    Object.values(nodes).forEach(node => {
      if (node.id === req.id) return;

      const parentReq = node.data.parent_requirement;
      if (parentReq === req.id) {
        packageNodes.push(node.id);
      }
    });

    packages.push({
      id: req.id,
      name: req.data.requirement_id || req.data.title?.substring(0, 30) || req.id,
      nodeIds: packageNodes
    });
  });

  return packages;
}

interface AppState {
  // State
  projects: Project[];
  currentProject: string | null;
  projectData: ProjectData | null;
  nodes: Record<string, CanvasNode>;
  connections: Connection[];
  diagrams: Diagram[];
  selectedNodeId: string | null;
  layoutMode: LayoutMode;
  error: string | null;
  loading: boolean;
  enterpriseOutputPath: string;

  // UI State
  sidebarCollapsed: boolean;
  zoom: number;
  panOffset: { x: number; y: number };

  // Actions
  loadProjects: () => Promise<void>;
  selectProject: (name: string) => Promise<void>;
  loadDiagrams: (projectName: string) => Promise<void>;
  selectNode: (id: string | null) => void;
  updateNodePosition: (id: string, x: number, y: number) => void;
  setLayoutMode: (mode: LayoutMode) => void;
  setError: (error: string | null) => void;
  clearError: () => void;
  setEnterpriseOutputPath: (path: string) => Promise<void>;

  // UI Actions
  toggleSidebar: () => void;
  setZoom: (zoom: number) => void;
  setPanOffset: (offset: { x: number; y: number }) => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  // Initial State
  projects: [],
  currentProject: null,
  projectData: null,
  nodes: {},
  connections: [],
  diagrams: [],
  selectedNodeId: null,
  layoutMode: 'package_link',
  error: null,
  loading: false,
  enterpriseOutputPath: '',

  // UI State
  sidebarCollapsed: false,
  zoom: 1,
  panOffset: { x: 0, y: 0 },

  // Actions
  loadProjects: async () => {
    set({ loading: true, error: null });
    try {
      const result = await window.api.projects.list();
      if (result.success) {
        set({ projects: result.data, loading: false });
      } else {
        set({ error: result.error, loading: false });
      }
    } catch (e) {
      set({
        error: e instanceof Error ? e.message : 'Failed to load projects',
        loading: false
      });
    }
  },

  selectProject: async (name) => {
    set({ loading: true, error: null, currentProject: name });
    try {
      const result = await window.api.projects.load(name);
      if (result.success) {
        const projectData = result.data as ProjectData;

        // Parse nodes from journal.json
        const nodes: Record<string, CanvasNode> = {};
        const connections: Connection[] = [];

        let index = 0;
        for (const [key, nodeData] of Object.entries(projectData.nodes || {})) {
          // Add the main node (requirement)
          nodes[key] = nodeDataToCanvasNode(key, nodeData, index);
          index++;

          // Extract embedded mermaid diagrams as separate nodes
          index = extractDiagramNodes(key, nodeData, nodes, connections, index);

          // Extract connections from dependencies
          if (nodeData.dependencies) {
            nodeData.dependencies.forEach(dep => {
              connections.push({
                id: `${key}-${dep}`,
                from: key,
                to: dep,
                type: 'dependency'
              });
            });
          }

          // Parent relationship
          if (nodeData.parent_requirement) {
            connections.push({
              id: `${key}-parent-${nodeData.parent_requirement}`,
              from: key,
              to: nodeData.parent_requirement,
              type: 'parent'
            });
          }
        }

        // Apply matrix layout to position nodes
        applyMatrixLayout(nodes, connections);

        set({
          projectData,
          nodes,
          connections,
          loading: false
        });

        // Also load diagrams from files
        await get().loadDiagrams(name);
      } else {
        set({ error: result.error, loading: false });
      }
    } catch (e) {
      set({
        error: e instanceof Error ? e.message : 'Failed to load project',
        loading: false
      });
    }
  },

  loadDiagrams: async (projectName) => {
    try {
      const result = await window.api.diagrams.list(projectName);
      if (result.success) {
        set({ diagrams: result.data as Diagram[] });
      }
    } catch (e) {
      console.error('Failed to load diagrams:', e);
    }
  },

  selectNode: (id) => set({ selectedNodeId: id }),

  updateNodePosition: (id, x, y) => {
    const { nodes } = get();
    if (nodes[id]) {
      set({
        nodes: {
          ...nodes,
          [id]: { ...nodes[id], x, y }
        }
      });
    }
  },

  setLayoutMode: (mode) => set({ layoutMode: mode }),

  setError: (error) => set({ error }),

  clearError: () => set({ error: null }),

  setEnterpriseOutputPath: async (path) => {
    const result = await window.api.config.setEnterpriseOutputPath(path);
    if (result.success) {
      set({ enterpriseOutputPath: path });
      // Reload projects with new path
      await get().loadProjects();
    } else {
      set({ error: result.error });
    }
  },

  // UI Actions
  toggleSidebar: () => set(state => ({ sidebarCollapsed: !state.sidebarCollapsed })),

  setZoom: (zoom) => set({ zoom: Math.max(0.1, Math.min(3, zoom)) }),

  setPanOffset: (offset) => set({ panOffset: offset })
}));

// Selector hooks for better performance
export const useProjects = () => useAppStore(state => state.projects);
export const useCurrentProject = () => useAppStore(state => state.currentProject);
export const useNodes = () => useAppStore(state => state.nodes);
export const useConnections = () => useAppStore(state => state.connections);
export const useDiagrams = () => useAppStore(state => state.diagrams);
export const useSelectedNode = () => useAppStore(state =>
  state.selectedNodeId ? state.nodes[state.selectedNodeId] : null
);
export const useLoading = () => useAppStore(state => state.loading);
export const useError = () => useAppStore(state => state.error);
export const useZoom = () => useAppStore(state => state.zoom);
export const useSelectedNodeId = () => useAppStore(state => state.selectedNodeId);
export const useLayoutMode = () => useAppStore(state => state.layoutMode);
export const useSidebarCollapsed = () => useAppStore(state => state.sidebarCollapsed);
