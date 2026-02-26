/**
 * Project Types for RE System Dashboard
 */

import type { NodeData } from './node';
import type { Connection } from './connection';

export interface Project {
  name: string;
  path: string;
  diagramCount: number;
  nodeCount: number;
  lastModified: Date;
}

export interface ProjectData {
  project_name: string;
  nodes: Record<string, NodeData>;
  connections?: Connection[];
  created_at?: string;
  updated_at?: string;
  version?: number;
}

export interface Diagram {
  filename: string;
  reqId: string;
  type: string;
  code: string;
}

export interface DiagramGroup {
  reqId: string;
  diagrams: Diagram[];
}
