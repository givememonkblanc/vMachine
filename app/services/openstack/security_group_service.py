from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import AppException
from app.schemas.openstack.security_group import (
    SecurityGroupCreateRequest,
    SecurityGroupRuleCreateRequest,
    SecurityGroupRuleSummary,
    SecurityGroupSummary,
)


class SecurityGroupService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory

    def list_security_groups(self) -> list[SecurityGroupSummary]:
        return [
            SecurityGroupSummary(
                id=sg.id, name=sg.name, description=getattr(sg, "description", "")
            )
            for sg in self.factory.call("network", "security_groups")
        ]

    def get_security_group(self, security_group_id: str) -> SecurityGroupSummary:
        sg = self.factory.call("network", "get_security_group", security_group_id)
        if not sg:
            raise AppException(
                message="Security group not found",
                status_code=404,
                error_code="security_group_not_found",
            )
        return SecurityGroupSummary(
            id=sg.id, name=sg.name, description=getattr(sg, "description", "")
        )

    def create_security_group(
        self, payload: SecurityGroupCreateRequest
    ) -> SecurityGroupSummary:
        sg = self.factory.call(
            "network",
            "create_security_group",
            name=payload.name,
            description=payload.description,
        )
        return SecurityGroupSummary(
            id=sg.id, name=sg.name, description=getattr(sg, "description", "")
        )

    def delete_security_group(self, security_group_id: str) -> None:
        deleted = self.factory.call(
            "network", "delete_security_group", security_group_id, ignore_missing=True
        )
        if deleted is False:
            raise AppException(
                message="Security group not found",
                status_code=404,
                error_code="security_group_not_found",
            )

    def list_rules(self, security_group_id: str) -> list[SecurityGroupRuleSummary]:
        sg = self.factory.call("network", "get_security_group", security_group_id)
        if not sg:
            raise AppException(
                message="Security group not found",
                status_code=404,
                error_code="security_group_not_found",
            )
        return [
            SecurityGroupRuleSummary(
                id=rule.id,
                direction=getattr(rule, "direction", ""),
                protocol=getattr(rule, "protocol", None),
                port_range_min=getattr(rule, "port_range_min", None),
                port_range_max=getattr(rule, "port_range_max", None),
                remote_ip_prefix=getattr(rule, "remote_ip_prefix", None),
                ethertype=getattr(rule, "ethertype", "IPv4"),
            )
            for rule in getattr(sg, "security_group_rules", [])
        ]

    def create_rule(
        self, payload: SecurityGroupRuleCreateRequest
    ) -> SecurityGroupRuleSummary:
        kwargs: dict[str, object] = {
            "direction": payload.direction,
            "protocol": payload.protocol,
            "ethertype": payload.ethertype or "IPv4",
        }
        if payload.port_range_min is not None:
            kwargs["port_range_min"] = payload.port_range_min
        if payload.port_range_max is not None:
            kwargs["port_range_max"] = payload.port_range_max
        if payload.remote_ip_prefix:
            kwargs["remote_ip_prefix"] = payload.remote_ip_prefix

        rule = self.factory.call("network", "create_security_group_rule", **kwargs)
        return SecurityGroupRuleSummary(
            id=rule.id,
            direction=getattr(rule, "direction", ""),
            protocol=getattr(rule, "protocol", None),
            port_range_min=getattr(rule, "port_range_min", None),
            port_range_max=getattr(rule, "port_range_max", None),
            remote_ip_prefix=getattr(rule, "remote_ip_prefix", None),
            ethertype=getattr(rule, "ethertype", "IPv4"),
        )

    def delete_rule(self, rule_id: str) -> None:
        deleted = self.factory.call(
            "network", "delete_security_group_rule", rule_id, ignore_missing=True
        )
        if deleted is False:
            raise AppException(
                message="Security group rule not found",
                status_code=404,
                error_code="rule_not_found",
            )
