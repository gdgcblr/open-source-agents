"""
Agent 1: The Topology & Dependency Graph Parser
Maps the infrastructure dependency graph and generates visual architecture diagrams.
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

                # Pattern looking for aws_<type>.<name> or simply the resource name
                ref_pattern = rf'(aws_[a-zA-Z0-9_]+\.{re.escape(target_name)}|{re.escape(target_name)})'
                if re.search(ref_pattern, source_res.raw_block):
                    if (source_res.resource_name, target_name) not in edge_keys:
                        edge_keys.add((source_res.resource_name, target_name))
                        rel = self._determine_relationship(source_res.resource_type, target_res.resource_type)
                        edges.append(DependencyEdge(
                            source=source_res.resource_name,
                            target=target_name,
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

    def _determine_relationship(self, src_type: str, tgt_type: str) -> str:
        if "iam" in tgt_type:
            return "assumes_identity"
        if "sqs" in tgt_type or "pubsub" in tgt_type:
            return "publishes_to"
        if "s3" in tgt_type or "storage" in tgt_type:
            return "stores_data_in"
        if "db" in tgt_type or "sql" in tgt_type:
            return "connects_to"
        return "references"

    def _generate_aws_mermaid(self, resources: List[AWSResource], edges: List[DependencyEdge]) -> str:
        lines = ["graph LR", "  subgraph AWS_Source_Architecture [AWS Infrastructure]"]
        for res in resources:
            icon_label = f"{res.resource_type}<br/><b>{res.resource_name}</b>"
            lines.append(f'    {res.resource_name}["{icon_label}"]')
        lines.append("  end")

        for edge in edges:
            lines.append(f"  {edge.source} -->|{edge.relationship}| {edge.target}")

        return "\n".join(lines)

    def _generate_gcp_mermaid(self, resources: List[AWSResource], edges: List[DependencyEdge]) -> str:
        lines = ["graph LR", "  subgraph GCP_Target_Architecture [Google Cloud Modernized Infrastructure]"]
        for res in resources:
            mapping = get_service_mapping(res.resource_type)
            gcp_label = f"{mapping['gcp_service']}<br/><b>{res.resource_name}</b>"
            lines.append(f'    gcp_{res.resource_name}["{gcp_label}"]')
        lines.append("  end")

        for edge in edges:
            lines.append(f"  gcp_{edge.source} -->|{edge.relationship}| gcp_{edge.target}")

        return "\n".join(lines)
