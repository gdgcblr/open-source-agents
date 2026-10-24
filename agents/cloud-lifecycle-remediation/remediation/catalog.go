package remediation

import (
	"fmt"
	"strings"
)

// EventMapping ties a deprecation event service label to Terraform scan/patch targets.
type EventMapping struct {
	ResourceType    string
	ValueAttribute  string
	GuidanceService string
}

// EventMappingForService resolves how to scan and patch from the event service field.
func EventMappingForService(service string) (EventMapping, error) {
	switch strings.ToUpper(strings.TrimSpace(service)) {
	case "EKS":
		return EventMapping{
			ResourceType:    "aws_eks_cluster",
			ValueAttribute:  "version",
			GuidanceService: "EKS",
		}, nil
	case "RDS":
		return EventMapping{
			ResourceType:    "aws_db_instance",
			ValueAttribute:  "engine_version",
			GuidanceService: "RDS",
		}, nil
	case "RDS_INSTANCE":
		return EventMapping{
			ResourceType:    "aws_db_instance",
			ValueAttribute:  "instance_class",
			GuidanceService: "RDS_INSTANCE",
		}, nil
	case "EC2":
		return EventMapping{
			ResourceType:    "aws_instance",
			ValueAttribute:  "instance_type",
			GuidanceService: "EC2",
		}, nil
	case "EKS_NODEGROUP":
		return EventMapping{
			ResourceType:    "aws_eks_node_group",
			ValueAttribute:  "instance_types",
			GuidanceService: "EKS_NODEGROUP",
		}, nil
	default:
		return EventMapping{}, fmt.Errorf("unsupported service %q (use EKS, RDS, RDS_INSTANCE, EC2, or EKS_NODEGROUP)", service)
	}
}
