/**
 * Type exports for RE System Dashboard
 */

export * from './node';
export * from './connection';
export * from './project';

// API Response types
export type ApiResponse<T> =
  | { success: true; data: T }
  | { success: false; error: string };

// Layout types
export type LayoutMode =
  | 'package_link'
  | 'link_based'
  | 'flow_based'
  | 'by_package'
  | 'raw_data';

// Notification types for change tracking
export interface ChangeNotification {
  id: string;
  nodeId: string;
  nodeType: string;
  changeType: 'content_edit' | 'structure_change' | 'diagram_update' | 'connection_change';
  changeDetails: Record<string, unknown>;
  affectedNodes: string[];
  timestamp: string;
  status: 'pending' | 'processing' | 'completed';
  responses: Record<string, AgentResponse>;
}

export interface AgentResponse {
  acknowledged: boolean;
  needsChange: boolean;
  changeApplied: boolean;
  reason: string;
  timestamp: string;
}
