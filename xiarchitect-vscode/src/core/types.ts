export interface XiArchitectTechnology {
  name: string;
  version?: string;
  confidence: number;
}

export interface XiArchitectStackSummary {
  languages: XiArchitectTechnology[];
  backend: XiArchitectTechnology[];
  frontend: XiArchitectTechnology[];
  database: XiArchitectTechnology[];
  cache: XiArchitectTechnology[];
  workers: XiArchitectTechnology[];
  overall_confidence: number;
}

export interface XiArchitectScanReport {
  workspace_root: string;
  total_files: number;
  classified_files: number;
  role_counts: Record<string, number>;
}

export interface XiArchitectRawGraph {
  nodes: Array<{ id: string }>;
  edges: Array<{ id: string }>;
}

export interface XiArchitectSnapshot {
  workspaceRoot: string;
  outputDir: string;
  scanReport: XiArchitectScanReport | null;
  stackSummary: XiArchitectStackSummary | null;
  rawGraph: XiArchitectRawGraph | null;
  diagrams: string[];
}
