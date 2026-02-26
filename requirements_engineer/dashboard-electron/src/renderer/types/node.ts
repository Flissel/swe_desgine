/**
 * Node Types for RE System Dashboard
 */

export type NodeType =
  | 'requirement'
  | 'epic'
  | 'user-story'
  | 'diagram'
  | 'test'
  | 'api'
  | 'component'
  | 'screen'
  | 'persona'
  | 'user-flow'
  | 'task'
  | 'tech-stack';

export type DiagramType =
  | 'flowchart'
  | 'sequence'
  | 'class'
  | 'er'
  | 'state'
  | 'c4';

export type ValidationStatus = 'draft' | 'review' | 'approved' | 'rejected';

export type Priority = 'must' | 'should' | 'could' | 'wont';

export interface MermaidDiagrams {
  flowchart?: string;
  sequence?: string;
  class?: string;
  er?: string;
  state?: string;
  c4?: string;
}

export interface NodeData {
  id: string;
  requirement_id?: string;
  title: string;
  description?: string;
  type?: string;
  priority?: Priority;
  rationale?: string;
  source?: string;
  acceptance_criteria?: string[];
  testable?: boolean;
  parent_requirement?: string | null;
  dependencies?: string[];
  conflicts?: string[];
  related_requirements?: string[];
  work_package?: string;
  estimated_effort?: number | null;
  assigned_to?: string | null;
  mermaid_diagrams?: MermaidDiagrams;
  mermaid_code?: string;
  diagram_type?: DiagramType;
  validation_status?: ValidationStatus;
  completeness_score?: number;
  consistency_score?: number;
  testability_score?: number;
  clarity_score?: number;
  feasibility_score?: number;
  traceability_score?: number;
  version?: number;
  created_at?: string;
  updated_at?: string;
  stage?: number;
  stage_name?: string;
  is_buggy?: boolean;
  is_complete?: boolean;
  quality_issues?: string[];
  improvement_suggestions?: string[];
  analysis?: string;
}

export interface CanvasNode {
  id: string;
  type: NodeType;
  data: NodeData;
  x: number;
  y: number;
  width: number;
  height: number;
  element?: HTMLElement;
}

export interface NodePosition {
  x: number;
  y: number;
}

export interface NodeDimensions {
  width: number;
  height: number;
}
