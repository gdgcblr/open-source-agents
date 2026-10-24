"""
Agent 1: The Topology & Dependency Graph Parser
Maps the infrastructure dependency graph and generates robust Mermaid architecture diagrams.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Set
from .parser import AWSResource
from .mapper import get_service_mapping


@dataclass
class DependencyEdge:
    source: str
    target: str
    relationship: str


@dataclass
class TopologyGraph:
    nodes: Dict[str, AWSResource]
    edges: List[DependencyEdge]
    aws_mermaid: str
    gcp_mermaid: str


class TopologyAgent:
    """Agent that discovers architectural dependencies and builds structural graphs."""

    def build_graph(self, resources: List[AWSResource]) -> TopologyGraph:
        resource_map: Dict[str, AWSResource] = {r.resource_name: r for r in resources}
        edges: List[DependencyEdge] = []
        edge_keys: Set[Tuple[str, str]] = set()

        # Find references in raw blocks to other resources
        for source_res in resources:
            for target_name, target_res in resource_map.items():
                if source_res.resource_name == target_name:
                    continue

                ref_pattern = rf'(aws_[a-zA-Z0-9_]+\.{re.escape(target_name)}|{re.escape(target_name)})'
                if re.search(ref_pattern, source_res.raw_block):
                    if (source_res.resource_name, target_name) not in edge_keys:
                        edge_keys.add((source_res.resource_name, target_name))
                        rel = self._determine_relationship(source_res.resource_type, target_res.resource_type)
                        edges.append(DependencyEdge(
                            source=self._clean_id(source_res.resource_name),
                            target=self._clean_id(target_name),
                            relationship=rel
                        ))

        aws_mermaid = self._generate_aws_mermaid(resources, edges)
        gcp_mermaid = self._generate_gcp_mermaid(resources, edges)

        return TopologyGraph(
            nodes=resource_map,
            edges=edges,
            aws_mermaid=aws_mermaid,
            gcp_mermaid=gcp_mermaid
        )

    def _clean_id(self, name: str) -> str:
        return re.sub(r'[^a-zA-Z0-9_]', '_', name)

    def _clean_label(self, label: str) -> str:
        # Strip parenthesis and special characters for Mermaid compatibility
        label = label.replace("(", "").replace(")", "").replace("<br/>", " - ").replace("<b>", "").replace("</b>", "")
        return label.replace('"', "'")

    def _determine_relationship(self, src_type: str, tgt_type: str) -> str:
        if "iam" in tgt_type:
            return "assumes"
        if "sqs" in tgt_type or "pubsub" in tgt_type:
            return "publishes"
        if "s3" in tgt_type or "storage" in tgt_type:
            return "stores_data"
        if "db" in tgt_type or "sql" in tgt_type:
            return "connects"
        return "routes"

    def _generate_aws_mermaid(self, resources: List[AWSResource], edges: List[DependencyEdge]) -> str:
        lines = ["flowchart TD", "  subgraph AWS_Source [AWS Cloud Architecture]"]
        for res in resources:
            nid = self._clean_id(res.resource_name)
            type_name = res.resource_type.replace("aws_", "").replace("_", " ").title()
            label = self._clean_label(f"{type_name}: {res.resource_name}")
            lines.append(f'    {nid}["{label}"]')
        lines.append("  end")

        for edge in edges:
            lines.append(f"  {edge.source} -->|{edge.relationship}| {edge.target}")

        return "\n".join(lines)

    def _generate_gcp_mermaid(self, resources: List[AWSResource], edges: List[DependencyEdge]) -> str:
        lines = ["flowchart TD", "  subgraph GCP_Target [Google Cloud Modernized Architecture]"]
        for res in resources:
            nid = f"gcp_{self._clean_id(res.resource_name)}"
            mapping = get_service_mapping(res.resource_type)
            service_name = mapping.get("gcp_service", "GCP Service")
            label = self._clean_label(f"{service_name}: {res.resource_name}")
            lines.append(f'    {nid}["{label}"]')
        lines.append("  end")

        for edge in edges:
            lines.append(f"  gcp_{edge.source} -->|{edge.relationship}| gcp_{edge.target}")

        return "\n".join(lines)
