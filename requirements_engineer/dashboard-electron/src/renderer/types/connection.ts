/**
 * Connection Types for RE System Dashboard
 */

export type ConnectionType = 'trace' | 'dependency' | 'parent' | 'related';

export interface Connection {
  id: string;
  from: string;
  to: string;
  type: ConnectionType;
  label?: string;
  color?: string;
  style?: 'solid' | 'dashed' | 'dotted';
}

export interface ConnectionPath {
  id: string;
  d: string;
  stroke: string;
  strokeWidth: number;
  markerEnd?: string;
}
