#!/usr/bin/env python3
"""
Gera um relatório JSON com evidências dos últimos backups por recurso AWS.

Este script usa a AWS CLI (comando `aws backup list-recovery-points-by-resource`)
para coletar dados de backup por ARN de recurso.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass
class BackupResource:
    """Representa um recurso monitorado para evidências de backup."""

    resource_type: str
    resource_arn: str


class AwsBackupEvidenceCollector:
    """Coletor de evidências de backup usando AWS CLI."""

    def __init__(
        self,
        resources: list[BackupResource],
        region: str = "us-east-1",
        profile: str | None = None,
        max_recovery_points: int = 10,
    ) -> None:
        self.resources = resources
        self.region = region
        self.profile = profile
        self.max_recovery_points = max_recovery_points

    def _build_aws_command(self, resource_arn: str) -> list[str]:
        command = [
            "aws",
            "backup",
            "list-recovery-points-by-resource",
            "--resource-arn",
            resource_arn,
            "--region",
            self.region,
            "--output",
            "json",
        ]

        if self.profile:
            command.extend(["--profile", self.profile])

        return command

    def _run_aws_cli(self, command: list[str]) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(command, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            return None

    @staticmethod
    def _parse_opensearch_domain_name(resource_arn: str) -> str | None:
        marker = ":domain/"
        if marker not in resource_arn:
            return None

        return resource_arn.split(marker, maxsplit=1)[1] or None

    @staticmethod
    def _parse_account_id(resource_arn: str) -> str | None:
        parts = resource_arn.split(":")
        if len(parts) < 5:
            return None
        return parts[4] or None

    def _collect_opensearch_snapshot_evidence(self, resource_arn: str) -> dict[str, Any]:
        domain_name = self._parse_opensearch_domain_name(resource_arn)
        account_id = self._parse_account_id(resource_arn)

        if not domain_name or not account_id:
            return {
                "status": "unavailable",
                "error": {
                    "type": "invalid_opensearch_arn",
                    "message": "Não foi possível extrair DomainName/AccountId do ARN OpenSearch.",
                },
            }

        describe_command = [
            "aws",
            "opensearch",
            "describe-domain",
            "--domain-name",
            domain_name,
            "--region",
            self.region,
            "--output",
            "json",
        ]
        if self.profile:
            describe_command.extend(["--profile", self.profile])

        describe_result = self._run_aws_cli(describe_command)
        domain_status: dict[str, Any] = {}
        domain_error: dict[str, Any] | None = None

        if describe_result is None:
            domain_error = {
                "type": "aws_cli_not_found",
                "message": "AWS CLI não encontrada para consulta do domínio OpenSearch.",
            }
        elif describe_result.returncode != 0:
            domain_error = {
                "type": "describe_domain_error",
                "message": "Falha ao consultar metadados do domínio OpenSearch.",
                "stderr": describe_result.stderr.strip(),
            }
        else:
            try:
                describe_payload = json.loads(describe_result.stdout or "{}")
                domain_payload = describe_payload.get("DomainStatus", {})
                domain_status = {
                    "domain_name": domain_payload.get("DomainName"),
                    "engine_version": domain_payload.get("EngineVersion"),
                    "processing": domain_payload.get("Processing"),
                    "created": domain_payload.get("Created"),
                    "deleted": domain_payload.get("Deleted"),
                    "endpoint": domain_payload.get("Endpoint"),
                    "arn": domain_payload.get("ARN"),
                }
            except json.JSONDecodeError:
                domain_error = {
                    "type": "describe_domain_invalid_json",
                    "message": "Resposta inválida no describe-domain do OpenSearch.",
                }

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=14)
        metric_command = [
            "aws",
            "cloudwatch",
            "get-metric-statistics",
            "--namespace",
            "AWS/ES",
            "--metric-name",
            "AutomatedSnapshotFailure",
            "--dimensions",
            f"Name=DomainName,Value={domain_name}",
            f"Name=ClientId,Value={account_id}",
            "--start-time",
            end_time.replace(microsecond=0).isoformat(),
            "--end-time",
            start_time.replace(microsecond=0).isoformat(),
            "--period",
            "86400",
            "--statistics",
            "Maximum",
            "--region",
            self.region,
            "--output",
            "json",
        ]
        metric_command[metric_command.index("--start-time") + 1] = start_time.replace(
            microsecond=0
        ).isoformat()
        metric_command[metric_command.index("--end-time") + 1] = end_time.replace(
            microsecond=0
        ).isoformat()

        if self.profile:
            metric_command.extend(["--profile", self.profile])

        metric_result = self._run_aws_cli(metric_command)
        metric_error: dict[str, Any] | None = None
        latest_datapoint: dict[str, Any] | None = None

        if metric_result is None:
            metric_error = {
                "type": "aws_cli_not_found",
                "message": "AWS CLI não encontrada para consulta de métricas CloudWatch.",
            }
        elif metric_result.returncode != 0:
            metric_error = {
                "type": "cloudwatch_metric_error",
                "message": "Falha ao consultar métrica AutomatedSnapshotFailure.",
                "stderr": metric_result.stderr.strip(),
            }
        else:
            try:
                metric_payload = json.loads(metric_result.stdout or "{}")
                datapoints = metric_payload.get("Datapoints", [])
                if isinstance(datapoints, list) and datapoints:
                    latest_datapoint = sorted(
                        datapoints,
                        key=lambda item: self._parse_iso_date(item.get("Timestamp")),
                        reverse=True,
                    )[0]
            except json.JSONDecodeError:
                metric_error = {
                    "type": "cloudwatch_metric_invalid_json",
                    "message": "Resposta inválida no get-metric-statistics.",
                }

        snapshot_health = "unknown"
        if latest_datapoint and latest_datapoint.get("Maximum") == 0:
            snapshot_health = "ok"
        elif latest_datapoint and latest_datapoint.get("Maximum") is not None:
            snapshot_health = "failure_detected"

        return {
            "status": "collected" if not metric_error else "partial",
            "source": "cloudwatch_automated_snapshot_metric",
            "domain_status": domain_status,
            "domain_error": domain_error,
            "metric": {
                "namespace": "AWS/ES",
                "metric_name": "AutomatedSnapshotFailure",
                "dimensions": {
                    "DomainName": domain_name,
                    "ClientId": account_id,
                },
                "window_days": 14,
                "latest_datapoint": latest_datapoint,
                "snapshot_health": snapshot_health,
                "error": metric_error,
            },
            "commands": {
                "describe_domain": " ".join(describe_command),
                "get_metric_statistics": " ".join(metric_command),
            },
            "collected_at": self._to_iso_utc(datetime.now(timezone.utc)),
        }

    @staticmethod
    def _is_not_supported_error(stderr_output: str) -> bool:
        normalized = (stderr_output or "").lower()
        return "the resource is not supported" in normalized

    @staticmethod
    def _parse_iso_date(date_value: str | None) -> datetime | None:
        if not date_value:
            return None

        normalized = date_value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None

    @staticmethod
    def _to_iso_utc(dt: datetime | None) -> str | None:
        if dt is None:
            return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc).isoformat()

    def _extract_latest_backup(
        self, recovery_points: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        if not recovery_points:
            return None

        sorted_points = sorted(
            recovery_points,
            key=lambda item: self._parse_iso_date(item.get("CreationDate"))
            or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        latest = sorted_points[0]
        return {
            "recovery_point_arn": latest.get("RecoveryPointArn"),
            "creation_date": latest.get("CreationDate"),
            "completion_date": latest.get("CompletionDate"),
            "status": latest.get("Status"),
            "backup_vault_name": latest.get("BackupVaultName"),
            "iam_role_arn": latest.get("IamRoleArn"),
            "resource_type": latest.get("ResourceType"),
            "resource_arn": latest.get("ResourceArn"),
            "is_parent": latest.get("IsParent"),
            "parent_recovery_point_arn": latest.get("ParentRecoveryPointArn"),
        }

    def _collect_for_resource(self, resource: BackupResource) -> dict[str, Any]:
        # Domínios OpenSearch usam snapshots automatizados gerenciados pelo serviço,
        # então coletamos evidência diretamente por OpenSearch + CloudWatch.
        if resource.resource_type == "opensearch":
            collected_at = self._to_iso_utc(datetime.now(timezone.utc))
            snapshot_evidence = self._collect_opensearch_snapshot_evidence(
                resource.resource_arn
            )

            latest_datapoint = (
                snapshot_evidence.get("metric", {}).get("latest_datapoint")
                if isinstance(snapshot_evidence, dict)
                else None
            )

            latest_backup = None
            if isinstance(latest_datapoint, dict):
                latest_backup = {
                    "source": "cloudwatch_automated_snapshot_metric",
                    "timestamp": latest_datapoint.get("Timestamp"),
                    "status": snapshot_evidence.get("metric", {}).get("snapshot_health"),
                    "metric_value": latest_datapoint.get("Maximum"),
                    "unit": latest_datapoint.get("Unit"),
                }

            return {
                "resource_type": resource.resource_type,
                "resource_arn": resource.resource_arn,
                "collected_at": collected_at,
                "status": "ok" if latest_backup else "partial",
                "backup_service": "opensearch_managed_snapshots",
                "collection_strategy": "opensearch_cloudwatch",
                "latest_backup": latest_backup,
                "alternative_snapshot_evidence": snapshot_evidence,
                "note": (
                    "OpenSearch não usa AWS Backup para este tipo de ARN. "
                    "As evidências foram coletadas por OpenSearch/CloudWatch."
                ),
            }

        command = self._build_aws_command(resource.resource_arn)
        collected_at = self._to_iso_utc(datetime.now(timezone.utc))

        try:
            process = subprocess.run(command, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            return {
                "resource_type": resource.resource_type,
                "resource_arn": resource.resource_arn,
                "collected_at": collected_at,
                "command": " ".join(command),
                "command_exit_code": None,
                "error": {
                    "type": "aws_cli_not_found",
                    "message": "AWS CLI não encontrada. Instale e configure o comando `aws`.",
                },
            }

        if process.returncode != 0:
            stderr_output = process.stderr.strip()
            stdout_output = process.stdout.strip()

            if self._is_not_supported_error(stderr_output):
                snapshot_evidence = None
                if resource.resource_type == "opensearch":
                    snapshot_evidence = self._collect_opensearch_snapshot_evidence(
                        resource.resource_arn
                    )

                return {
                    "resource_type": resource.resource_type,
                    "resource_arn": resource.resource_arn,
                    "collected_at": collected_at,
                    "command": " ".join(command),
                    "command_exit_code": process.returncode,
                    "stderr": stderr_output,
                    "stdout": stdout_output,
                    "status": "resource_not_supported_by_aws_backup",
                    "backup_service": "aws_backup",
                    "latest_backup": None,
                    "alternative_snapshot_evidence": snapshot_evidence,
                    "note": (
                        "O recurso não é suportado pelo AWS Backup para esta consulta. "
                        "A evidência foi registrada e a coleta pode continuar com outros recursos."
                    ),
                }

            return {
                "resource_type": resource.resource_type,
                "resource_arn": resource.resource_arn,
                "collected_at": collected_at,
                "command": " ".join(command),
                "command_exit_code": process.returncode,
                "stderr": stderr_output,
                "stdout": stdout_output,
                "status": "error",
                "error": {
                    "type": "aws_cli_command_error",
                    "message": "Falha ao consultar backups com AWS CLI.",
                },
            }

        try:
            payload = json.loads(process.stdout or "{}")
        except json.JSONDecodeError:
            return {
                "resource_type": resource.resource_type,
                "resource_arn": resource.resource_arn,
                "collected_at": collected_at,
                "command": " ".join(command),
                "command_exit_code": process.returncode,
                "stdout": process.stdout.strip(),
                "stderr": process.stderr.strip(),
                "status": "error",
                "error": {
                    "type": "invalid_json_response",
                    "message": "A resposta da AWS CLI não é um JSON válido.",
                },
            }

        recovery_points = payload.get("RecoveryPoints", [])
        if not isinstance(recovery_points, list):
            recovery_points = []

        latest_backup = self._extract_latest_backup(recovery_points)

        return {
            "resource_type": resource.resource_type,
            "resource_arn": resource.resource_arn,
            "collected_at": collected_at,
            "command": " ".join(command),
            "command_exit_code": process.returncode,
            "status": "ok",
            "recovery_points_found": len(recovery_points),
            "latest_backup": latest_backup,
            "evidence": {
                "sample_recovery_points": recovery_points[: self.max_recovery_points],
                "truncated": len(recovery_points) > self.max_recovery_points,
            },
        }

    def collect(self) -> dict[str, Any]:
        results = [self._collect_for_resource(resource) for resource in self.resources]

        total = len(results)
        with_backup = sum(1 for item in results if item.get("latest_backup"))
        with_error = sum(1 for item in results if item.get("error"))
        unsupported = sum(
            1 for item in results if item.get("status") == "resource_not_supported_by_aws_backup"
        )

        return {
            "generated_at": self._to_iso_utc(datetime.now(timezone.utc)),
            "region": self.region,
            "resources": [asdict(resource) for resource in self.resources],
            "reports": results,
            "summary": {
                "total_resources": total,
                "resources_with_backup": with_backup,
                "resources_without_backup": total - with_backup - with_error - unsupported,
                "resources_not_supported_by_aws_backup": unsupported,
                "resources_with_error": with_error,
            },
        }


def _build_default_resources() -> list[BackupResource]:
    return [
        BackupResource(
            resource_type="opensearch",
            resource_arn="arn:aws:es:us-east-1:578416043364:domain/search-service",
        )
    ]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Coleta evidências dos últimos backups via AWS CLI e gera JSON consolidado.",
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="Região AWS para consulta dos backups (default: us-east-1).",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="AWS profile opcional para execução da CLI.",
    )
    parser.add_argument(
        "--output",
        default="backup_evidence_report.json",
        help="Caminho do arquivo JSON de saída.",
    )
    parser.add_argument(
        "--max-recovery-points",
        type=int,
        default=10,
        help="Quantidade máxima de recovery points por recurso no bloco de evidências.",
    )
    parser.add_argument(
        "--add-resource",
        action="append",
        nargs=2,
        metavar=("RESOURCE_TYPE", "RESOURCE_ARN"),
        help=(
            "Adiciona recursos extras ao relatório. Pode ser usado múltiplas vezes, "
            "ex.: --add-resource rds arn:... --add-resource dynamodb arn:..."
        ),
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    resources = _build_default_resources()

    if args.add_resource:
        for resource_type, resource_arn in args.add_resource:
            resources.append(
                BackupResource(
                    resource_type=resource_type.lower(),
                    resource_arn=resource_arn,
                )
            )

    collector = AwsBackupEvidenceCollector(
        resources=resources,
        region=args.region,
        profile=args.profile,
        max_recovery_points=max(1, args.max_recovery_points),
    )
    report = collector.collect()

    output_path = Path(args.output)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Relatório gerado em: {output_path}")
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Execução interrompida pelo usuário.", file=sys.stderr)
        sys.exit(130)
