"""
Google Agent Development Kit (ADK) Adapter
Provides a formal Google ADK-compliant Tool & Agent Orchestration layer.
"""

import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from .parser import TerraformParser, AWSResource
from .topology_agent import TopologyAgent, TopologyGraph
from .finops_agent import FinOpsPredictorAgent, FinOpsReport
from .generator import MigrationGenerator


@dataclass
class ADKToolDeclaration:
    name: str
    description: str
    parameters: Dict[str, Any]


class GoogleADKMigrationAgent:
    """
    Google Agent Development Kit (ADK) Compliant Orchestration Agent.
    Implements standard ADK Tool Calling, State Management, and Multi-Agent Reasoning.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-3.8-flash",
        project_id: str = "fintech-enterprise-gcp",
        region: str = "us-central1"
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model_name = model_name or os.getenv("MODEL_NAME", "gemini-3.8-flash")
        self.project_id = project_id
        self.region = region

        # ADK Tools
        self.topology_tool = TopologyAgent()
        self.finops_tool = FinOpsPredictorAgent()
        self.generator_tool = MigrationGenerator(project_id=self.project_id, region=self.region)

    def get_tool_declarations(self) -> List[ADKToolDeclaration]:
        """Returns standard Google ADK / Gemini Tool declarations."""
        return [
            ADKToolDeclaration(
                name="parse_infrastructure_topology",
                description="Discovers AWS resource dependencies and generates structural Mermaid architecture graphs.",
                parameters={
                    "type": "object",
                    "properties": {
                        "resources": {"type": "array", "description": "List of AWS infrastructure resources"}
                    },
                    "required": ["resources"]
                }
            ),
            ADKToolDeclaration(
                name="predict_finops_tco",
                description="Calculates AWS vs Google Cloud Total Cost of Ownership (TCO) and net savings delta.",
                parameters={
                    "type": "object",
                    "properties": {
                        "resources": {"type": "array", "description": "List of AWS infrastructure resources"}
                    },
                    "required": ["resources"]
                }
            ),
            ADKToolDeclaration(
                name="generate_gcp_terraform",
                description="Transpiles AWS infrastructure definitions into idiomatic Google Cloud Terraform HCL.",
                parameters={
                    "type": "object",
                    "properties": {
                        "resources": {"type": "array", "description": "List of AWS infrastructure resources"},
                        "target_project": {"type": "string", "description": "GCP Project ID"},
                        "target_region": {"type": "string", "description": "GCP Region"}
                    },
                    "required": ["resources"]
                }
            )
        ]

    def execute_adk_pipeline(
        self,
        input_path: str,
        output_dir: str = "output"
    ) -> Dict[str, Any]:
        """
        Executes the Google ADK multi-agent workflow:
        1. Tool Execution: Parse Topology & Dependencies
        2. Tool Execution: Predict FinOps TCO & Free Tier Impact
        3. Tool Execution: Transpile GCP Terraform HCL
        4. Gemini LLM Synthesis & Strategic Architectural Review
        """
        parser = TerraformParser()
        resources = parser.parse_file(input_path)

        with open(input_path, "r", encoding="utf-8") as f:
            raw_code = f.read()

        # Step 1: ADK Topology Tool
        topology_graph = self.topology_tool.build_graph(resources)

        # Step 2: ADK FinOps Tool
        finops_report = self.finops_tool.predict_tco(resources)

        # Step 3: ADK Terraform Generator Tool
        gcp_terraform = self.generator_tool.generate_terraform(resources)

        return {
            "resources": resources,
            "topology": topology_graph,
            "finops": finops_report,
            "terraform": gcp_terraform,
            "raw_code": raw_code
        }
