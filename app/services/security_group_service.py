from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import AppException, OpenStackIntegrationException
from app.common.utils.serializers import serialize_resource
from app.schemas.security_group import (
    SecurityGroupCreateRequest,
    SecurityGroupCreateResponse,
    SecurityGroupDetail,
    SecurityGroupRuleCreateRequest,
    SecurityGroupRuleCreateResponse,
    SecurityGroupRuleSummary,
    SecurityGroupSummary,
)


class SecurityGroupService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory

    def list_security_groups(self) -> list[SecurityGroupSummary]:
        conn = self.factory.create()
        try:
            return [
                SecurityGroupSummary(**serialize_resource(sg, ["id", "name", "description", "project_id"]))
                for sg in conn.network.security_groups()
            ]
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to list security groups: {exc}") from exc

    def get_security_group(self, security_group_id: str) -> SecurityGroupDetail:
        conn = self.factory.create()
        try:
            sg = conn.network.get_security_group(security_group_id)
            if not sg:
                raise AppException(message="Security group not found", status_code=404, error_code="sg_not_found")
            
            rules = []
            for rule in getattr(sg, "security_group_rules", []) or []:
                rules.append(
                    SecurityGroupRuleSummary(
                        **serialize_resource(
                            rule,
                            ["id", "security_group_id", "direction", "ethertype", "protocol", "port_range_min", "port_range_max", "remote_ip_prefix"],
                        )
                    )
                )
            
            return SecurityGroupDetail(
                **serialize_resource(sg, ["id", "name", "description", "project_id"]),
                rules=rules,
            )
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to get security group: {exc}") from exc

    def create_security_group(self, payload: SecurityGroupCreateRequest) -> SecurityGroupCreateResponse:
        conn = self.factory.create()
        try:
            sg = conn.network.create_security_group(name=payload.name, description=payload.description)
            return SecurityGroupCreateResponse(security_group_id=sg.id, name=sg.name)
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to create security group: {exc}") from exc

    def delete_security_group(self, security_group_id: str) -> None:
        conn = self.factory.create()
        try:
            deleted = conn.network.delete_security_group(security_group_id, ignore_missing=True)
            if deleted is False:
                raise AppException(message="Security group not found", status_code=404, error_code="sg_not_found")
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to delete security group: {exc}") from exc

    def create_rule(self, security_group_id: str, payload: SecurityGroupRuleCreateRequest) -> SecurityGroupRuleCreateResponse:
        conn = self.factory.create()
        try:
            sg = conn.network.get_security_group(security_group_id)
            if not sg:
                raise AppException(message="Security group not found", status_code=404, error_code="sg_not_found")

            kwargs = {
                "security_group_id": security_group_id,
                "direction": payload.direction,
                "ethertype": payload.ethertype,
            }
            if payload.protocol:
                kwargs["protocol"] = payload.protocol
            if payload.port_range_min is not None:
                kwargs["port_range_min"] = payload.port_range_min
            if payload.port_range_max is not None:
                kwargs["port_range_max"] = payload.port_range_max
            if payload.remote_ip_prefix:
                kwargs["remote_ip_prefix"] = payload.remote_ip_prefix

            rule = conn.network.create_security_group_rule(**kwargs)
            return SecurityGroupRuleCreateResponse(rule_id=rule.id)
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to create security group rule: {exc}") from exc

    def delete_rule(self, rule_id: str) -> None:
        conn = self.factory.create()
        try:
            deleted = conn.network.delete_security_group_rule(rule_id, ignore_missing=True)
            if deleted is False:
                raise AppException(message="Security group rule not found", status_code=404, error_code="sg_rule_not_found")
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to delete security group rule: {exc}") from exc
