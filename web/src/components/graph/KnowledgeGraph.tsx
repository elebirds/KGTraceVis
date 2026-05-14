import { Empty } from "@arco-design/web-react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import { useMemo } from "react";

import type {
  KGStudioGraphEdge,
  KGStudioGraphNode,
  PathGraphPath
} from "../../api/contracts";
import { valueText } from "../../api/format";

export interface GraphNodeView {
  id: string;
  label: string;
  category: string;
  scenario?: string;
  description?: string;
  x?: number;
  y?: number;
  raw?: unknown;
}

export interface GraphEdgeView {
  id: string;
  source: string;
  target: string;
  relation: string;
  confidence?: number | null;
  reviewStatus?: string | null;
  targetKey?: string;
  raw?: unknown;
}

export type GraphLayoutMode = "force" | "path";
export type GraphEdgeLabelMode = "selected" | "highlighted" | "all" | "none";

const PATH_LAYOUT_MIN_WIDTH = 720;
const PATH_LAYOUT_HORIZONTAL_PADDING = 120;
const PATH_LAYOUT_VIEWPORT_MARGIN_X = 260;
const PATH_LAYOUT_VIEWPORT_MARGIN_Y = 110;
const PATH_LAYOUT_BASE_Y = 150;
const PATH_LAYOUT_LANE_GAP = 76;
const PATH_LAYOUT_MIN_NODE_GAP = 170;
const PATH_LAYOUT_BOUNDARY_PREFIX = "__path_layout_boundary__";

export interface KnowledgeGraphProps {
  nodes: GraphNodeView[];
  edges: GraphEdgeView[];
  selectedTargetKey?: string;
  highlightedNodeIds?: string[];
  highlightedEdgeIds?: string[];
  showLabels?: boolean;
  showLegend?: boolean;
  edgeLabelMode?: GraphEdgeLabelMode;
  layoutMode?: GraphLayoutMode;
  height?: number;
  onSelectEdge?: (edge: GraphEdgeView) => void;
  onSelectNode?: (node: GraphNodeView) => void;
}

export function KnowledgeGraph({
  nodes,
  edges,
  selectedTargetKey,
  highlightedNodeIds = [],
  highlightedEdgeIds = [],
  showLabels = true,
  showLegend = true,
  edgeLabelMode = "selected",
  layoutMode = "force",
  height = 520,
  onSelectEdge,
  onSelectNode
}: KnowledgeGraphProps) {
  const option = useMemo(
    () =>
      buildGraphOption({
        nodes,
        edges,
        selectedTargetKey,
        highlightedNodeIds,
        highlightedEdgeIds,
        showLabels,
        showLegend,
        edgeLabelMode,
        layoutMode
      }),
    [
      edgeLabelMode,
      edges,
      highlightedEdgeIds,
      highlightedNodeIds,
      layoutMode,
      nodes,
      selectedTargetKey,
      showLabels,
      showLegend
    ]
  );

  if (!nodes.length || !edges.length) {
    return <Empty description="No graph data is available for this selection." />;
  }

  return (
    <ReactECharts
      option={option}
      style={{ height, width: "100%" }}
      notMerge
      lazyUpdate
      onEvents={{
        click: (params: unknown) => {
          const event = params as {
            dataType?: string;
            data?: { id?: string; targetKey?: string };
          };
          if (event.dataType === "edge") {
            const edge = edges.find(
              (item) =>
                item.id === event.data?.id ||
                (event.data?.targetKey && item.targetKey === event.data.targetKey)
            );
            if (edge) onSelectEdge?.(edge);
            return;
          }
          if (event.dataType === "node") {
            const node = nodes.find((item) => item.id === event.data?.id);
            if (node) onSelectNode?.(node);
          }
        }
      }}
    />
  );
}

export function graphFromKGStudio(
  graphNodes: KGStudioGraphNode[],
  graphEdges: KGStudioGraphEdge[]
): { nodes: GraphNodeView[]; edges: GraphEdgeView[] } {
  const nodeRows = new Map<string, GraphNodeView>();
  for (const node of graphNodes) {
    nodeRows.set(node.node_id, {
      id: node.node_id,
      label: node.label || node.node_id,
      category: node.node_type || "Unknown",
      scenario: node.scenario,
      description: node.description,
      raw: node
    });
  }
  for (const edge of graphEdges) {
    if (!nodeRows.has(edge.head)) {
      nodeRows.set(edge.head, {
        id: edge.head,
        label: edge.head,
        category: "Unknown",
        scenario: edge.scenario
      });
    }
    if (!nodeRows.has(edge.tail)) {
      nodeRows.set(edge.tail, {
        id: edge.tail,
        label: edge.tail,
        category: "Unknown",
        scenario: edge.scenario
      });
    }
  }
  return {
    nodes: Array.from(nodeRows.values()),
    edges: graphEdges.map((edge) => ({
      id: edge.edge_id,
      source: edge.head,
      target: edge.tail,
      relation: edge.relation,
      confidence: edge.confidence,
      reviewStatus: edge.review_status,
      targetKey: edge.target_key,
      raw: edge
    }))
  };
}

export function graphFromPath(path: PathGraphPath | undefined): {
  nodes: GraphNodeView[];
  edges: GraphEdgeView[];
} {
  if (!path) return { nodes: [], edges: [] };
  return {
    nodes: path.nodes.map((node) => ({
      id: node.node_id,
      label: node.label || node.node_id,
      category: node.role || "path",
      raw: node
    })),
    edges: path.edges.map((edge) => ({
      id: edge.edge_id,
      source: edge.source_node_id,
      target: edge.target_node_id,
      relation: edge.relation,
      confidence: edge.confidence,
      reviewStatus: edge.review_status,
      targetKey: edge.target_key,
      raw: edge
    }))
  };
}

function buildPathViewportBoundaryNodes(
  points: Array<{ node: GraphNodeView; x: number; y: number }>
) {
  const minX = Math.min(...points.map((point) => point.x));
  const maxX = Math.max(...points.map((point) => point.x));
  const minY = Math.min(...points.map((point) => point.y));
  const maxY = Math.max(...points.map((point) => point.y));
  return [
    [minX - PATH_LAYOUT_VIEWPORT_MARGIN_X, minY - PATH_LAYOUT_VIEWPORT_MARGIN_Y],
    [maxX + PATH_LAYOUT_VIEWPORT_MARGIN_X, minY - PATH_LAYOUT_VIEWPORT_MARGIN_Y],
    [minX - PATH_LAYOUT_VIEWPORT_MARGIN_X, maxY + PATH_LAYOUT_VIEWPORT_MARGIN_Y],
    [maxX + PATH_LAYOUT_VIEWPORT_MARGIN_X, maxY + PATH_LAYOUT_VIEWPORT_MARGIN_Y]
  ].map(([x, y], index) => ({
    id: `${PATH_LAYOUT_BOUNDARY_PREFIX}${index}`,
    name: "",
    x,
    y,
    value: [x, y],
    fixed: true,
    silent: true,
    symbolSize: 1,
    tooltip: { show: false },
    label: { show: false },
    itemStyle: { opacity: 0 },
    emphasis: { disabled: true }
  }));
}

function buildGraphOption({
  nodes,
  edges,
  selectedTargetKey,
  highlightedNodeIds,
  highlightedEdgeIds,
  showLabels,
  showLegend,
  edgeLabelMode,
  layoutMode
}: Required<
  Pick<
    KnowledgeGraphProps,
    | "nodes"
    | "edges"
    | "highlightedNodeIds"
    | "highlightedEdgeIds"
    | "showLabels"
    | "showLegend"
    | "edgeLabelMode"
    | "layoutMode"
  >
> &
  Pick<KnowledgeGraphProps, "selectedTargetKey">): EChartsOption {
  const categories = Array.from(new Set(nodes.map((node) => node.category || "Unknown"))).map(
    (name) => ({ name })
  );
  const degree = new Map<string, number>();
  for (const edge of edges) {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
  }
  const hasSelection = Boolean(selectedTargetKey);
  const selectedEdge = edges.find((edge) => edge.targetKey === selectedTargetKey);
  const focusedEdgeIds = new Set(highlightedEdgeIds);
  const focusedNodeIds = new Set(highlightedNodeIds);
  if (selectedEdge) {
    focusedEdgeIds.add(selectedEdge.id);
    focusedNodeIds.add(selectedEdge.source);
    focusedNodeIds.add(selectedEdge.target);
  }
  const hasFocus = focusedEdgeIds.size > 0 || focusedNodeIds.size > 0;
  const isPathLayout = layoutMode === "path";
  const pathLayoutWidth = Math.max(
    PATH_LAYOUT_MIN_WIDTH,
    PATH_LAYOUT_HORIZONTAL_PADDING * 2 + Math.max(0, nodes.length - 1) * PATH_LAYOUT_MIN_NODE_GAP
  );
  const pathNodeGap =
    nodes.length > 1
      ? (pathLayoutWidth - PATH_LAYOUT_HORIZONTAL_PADDING * 2) / (nodes.length - 1)
      : 0;
  const pathNodePoints = nodes.map((node, index) => ({
    node,
    x:
      node.x ??
      (nodes.length > 1
        ? PATH_LAYOUT_HORIZONTAL_PADDING + index * pathNodeGap
        : pathLayoutWidth / 2),
    y: node.y ?? PATH_LAYOUT_BASE_Y + (index % 2) * PATH_LAYOUT_LANE_GAP
  }));
  const pathViewportNodes =
    isPathLayout && pathNodePoints.length > 0
      ? buildPathViewportBoundaryNodes(pathNodePoints)
      : [];

  return {
    color: ["#165dff", "#00b42a", "#ff7d00", "#722ed1", "#f53f3f", "#14c9c9", "#86909c"],
    tooltip: {
      confine: true,
      formatter: (params: unknown) => {
        const item = params as {
          dataType?: string;
          data?: {
            name?: string;
            displayLabel?: string;
            relation?: string;
            confidence?: number | null;
            reviewStatus?: string | null;
            scenario?: string;
            description?: string;
          };
        };
        if (item.dataType === "edge") {
          return [
            `<strong>${valueText(item.data?.relation)}</strong>`,
            `confidence: ${valueText(item.data?.confidence)}`,
            `review: ${valueText(item.data?.reviewStatus)}`
          ].join("<br/>");
        }
        return [
          `<strong>${valueText(item.data?.displayLabel ?? item.data?.name)}</strong>`,
          `scenario: ${valueText(item.data?.scenario)}`,
          valueText(item.data?.description)
        ].join("<br/>");
      }
    },
    legend: showLegend
      ? {
          type: "scroll",
          bottom: 0,
          data: categories.map((item) => item.name)
        }
      : undefined,
    series: [
      {
        type: "graph",
        layout: isPathLayout ? "none" : "force",
        roam: !isPathLayout,
        draggable: !isPathLayout,
        focusNodeAdjacency: true,
        categories,
        left: isPathLayout ? 20 : undefined,
        right: isPathLayout ? 20 : undefined,
        top: isPathLayout ? 32 : undefined,
        bottom: isPathLayout ? 32 : undefined,
        force: isPathLayout
          ? undefined
          : {
              repulsion: 260,
              edgeLength: [90, 170],
              gravity: 0.08
            },
        label: {
          show: showLabels,
          position: isPathLayout ? "bottom" : "right",
          formatter: "{b}",
          fontSize: 11,
          distance: isPathLayout ? 8 : 5
        },
        edgeSymbol: ["none", "arrow"],
        edgeSymbolSize: [0, 8],
        lineStyle: {
          color: "source",
          curveness: isPathLayout ? 0.03 : 0.14,
          opacity: hasFocus || hasSelection ? 0.16 : 0.62
        },
        emphasis: {
          focus: "adjacency",
          label: { show: true },
          lineStyle: { width: 4, opacity: 0.96 }
        },
        data: [
          ...pathViewportNodes,
          ...pathNodePoints.map(({ node, x, y }) => {
            const focused = focusedNodeIds.has(node.id);
            return {
              id: node.id,
              name: node.label,
              displayLabel: node.label,
              category: node.category,
              scenario: node.scenario,
              description: node.description,
              x: isPathLayout ? x : undefined,
              y: isPathLayout ? y : undefined,
              value: isPathLayout ? [x, y] : undefined,
              fixed: isPathLayout ? true : undefined,
              symbolSize: isPathLayout
                ? node.category === "target"
                  ? 52
                  : node.category === "source"
                    ? 46
                    : 38
                : Math.min(52, 24 + (degree.get(node.id) ?? 0) * 4),
              label: {
                show: showLabels || focused
              },
              itemStyle:
                hasFocus && focused
                  ? { borderColor: "#f53f3f", borderWidth: 4, opacity: 1 }
                  : hasFocus
                    ? { opacity: 0.18 }
                    : undefined
            };
          })
        ],
        links: edges.map((edge) => {
          const selected = edge.targetKey === selectedTargetKey;
          const highlighted = focusedEdgeIds.has(edge.id);
          const showEdgeLabel =
            edgeLabelMode === "all" ||
            (edgeLabelMode === "highlighted" && highlighted) ||
            (edgeLabelMode === "selected" && selected);
          return {
            id: edge.id,
            source: edge.source,
            target: edge.target,
            relation: edge.relation,
            confidence: edge.confidence,
            reviewStatus: edge.reviewStatus,
            targetKey: edge.targetKey,
            label: {
              show: showEdgeLabel,
              formatter: edge.relation,
              fontSize: 10
            },
            lineStyle: {
              width: selected ? 5 : highlighted ? 3.5 : hasFocus ? 1 : Math.max(1, (edge.confidence ?? 0.5) * 3),
              opacity: selected ? 0.98 : highlighted ? 0.82 : hasFocus ? 0.1 : 0.58,
              color: selected ? "#f53f3f" : highlighted ? "#165dff" : undefined
            }
          };
        })
      }
    ]
  };
}
