#!/usr/bin/env python3
"""
Módulo de coleta de evidências de backup de recursos AWS.

Pode ser importado por outras aplicações (ex.: Streamlit) ou executado
diretamente via CLI para gerar um relatório JSON consolidado.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()


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

    def _run_command(self, command: list[str]) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(command, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            return None

    def _sanitize_command(self, command: list[str]) -> str:
        sanitized = command[:]
        if "--user" in sanitized:
            user_index = sanitized.index("--user")
            if user_index + 1 < len(sanitized):
                sanitized[user_index + 1] = "<redacted>"

        if "--header" in sanitized:
            indexes = [idx for idx, value in enumerate(sanitized) if value == "--header"]
            for header_index in indexes:
                if header_index + 1 < len(sanitized):
                    header_value = sanitized[header_index + 1].lower()
                    if "x-amz-security-token" in header_value:
                        sanitized[header_index + 1] = "x-amz-security-token: <redacted>"

        return " ".join(sanitized)

    def _resolve_sigv4_credentials(self) -> tuple[str, str, str | None] | None:
        access_key = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
        session_token = os.getenv("AWS_SESSION_TOKEN", "").strip() or None

        if access_key and secret_key:
            return access_key, secret_key, session_token

        export_command = [
            "aws",
            "configure",
            "export-credentials",
            "--format",
            "process",
        ]
        if self.profile:
            export_command.extend(["--profile", self.profile])

        export_result = self._run_aws_cli(export_command)
        if export_result is None or export_result.returncode != 0:
            return None

        try:
            credentials_payload = json.loads(export_result.stdout or "{}")
        except json.JSONDecodeError:
            return None

        access_key = credentials_payload.get("AccessKeyId", "").strip()
        secret_key = credentials_payload.get("SecretAccessKey", "").strip()
        session_token = credentials_payload.get("SessionToken", "").strip() or None

        if not access_key or not secret_key:
            return None

        return access_key, secret_key, session_token

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

    @staticmethod
    def _extract_opensearch_endpoint(domain_payload: dict[str, Any]) -> str | None:
        endpoint = domain_payload.get("Endpoint")
        if endpoint:
            return f"https://{endpoint}"

        endpoints = domain_payload.get("Endpoints")
        if isinstance(endpoints, dict):
            preferred = endpoints.get("vpc") or endpoints.get("VPC")
            if preferred:
                return f"https://{preferred}"
            if endpoints:
                first_value = next(iter(endpoints.values()))
                if isinstance(first_value, str) and first_value:
                    return f"https://{first_value}"

        return None

    def _build_sigv4_curl_command(self, url: str) -> list[str] | None:
        credentials = self._resolve_sigv4_credentials()
        if credentials is None:
            return None

        access_key, secret_key, session_token = credentials

        command = [
            "curl",
            "--silent",
            "--show-error",
            "--fail-with-body",
            "--aws-sigv4",
            f"aws:amz:{self.region}:es",
            "--user",
            f"{access_key}:{secret_key}",
            url,
        ]

        if session_token:
            command.extend(["--header", f"x-amz-security-token: {session_token}"])

        return command

    def _collect_opensearch_snapshot_evidence(self, resource_arn: str) -> dict[str, Any]:
        domain_name = self._parse_opensearch_domain_name(resource_arn)

        if not domain_name:
            return {
                "status": "unavailable",
                "error": {
                    "type": "invalid_opensearch_domain_arn",
                    "message": "Não foi possível extrair DomainName do ARN OpenSearch.",
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
                endpoint_url = self._extract_opensearch_endpoint(domain_payload)
                domain_status = {
                    "domain_name": domain_payload.get("DomainName"),
                    "engine_version": domain_payload.get("EngineVersion"),
                    "processing": domain_payload.get("Processing"),
                    "created": domain_payload.get("Created"),
                    "deleted": domain_payload.get("Deleted"),
                    "endpoint": domain_payload.get("Endpoint"),
                    "endpoints": domain_payload.get("Endpoints"),
                    "endpoint_url": endpoint_url,
                    "arn": domain_payload.get("ARN"),
                }
            except json.JSONDecodeError:
                domain_error = {
                    "type": "describe_domain_invalid_json",
                    "message": "Resposta inválida no describe-domain do OpenSearch.",
                }

        endpoint_url = domain_status.get("endpoint_url") if domain_status else None
        if not endpoint_url:
            return {
                "status": "partial",
                "source": "opensearch_snapshot_api",
                "domain_status": domain_status,
                "domain_error": domain_error,
                "snapshot_api": {
                    "error": {
                        "type": "missing_domain_endpoint",
                        "message": "Não foi possível identificar o endpoint do domínio OpenSearch.",
                    }
                },
                "collected_at": self._to_iso_utc(datetime.now(timezone.utc)),
            }

        list_repos_url = f"{endpoint_url}/_snapshot"
        repo_command = self._build_sigv4_curl_command(list_repos_url)
        if repo_command is None:
            return {
                "status": "partial",
                "source": "opensearch_snapshot_api",
                "domain_status": domain_status,
                "domain_error": domain_error,
                "snapshot_api": {
                    "error": {
                        "type": "missing_sigv4_credentials",
                        "message": (
                            "Não foi possível obter credenciais AWS para consulta da API de "
                            "snapshots com assinatura SigV4."
                        ),
                    }
                },
                "collected_at": self._to_iso_utc(datetime.now(timezone.utc)),
            }

        repo_result = self._run_command(repo_command)
        if repo_result is None:
            return {
                "status": "partial",
                "source": "opensearch_snapshot_api",
                "domain_status": domain_status,
                "domain_error": domain_error,
                "snapshot_api": {
                    "error": {
                        "type": "curl_not_found",
                        "message": "Comando curl não encontrado para chamada da API de snapshots.",
                    },
                    "commands": {
                        "list_repositories": self._sanitize_command(repo_command)
                    },
                },
                "collected_at": self._to_iso_utc(datetime.now(timezone.utc)),
            }

        if repo_result.returncode != 0:
            return {
                "status": "partial",
                "source": "opensearch_snapshot_api",
                "domain_status": domain_status,
                "domain_error": domain_error,
                "snapshot_api": {
                    "error": {
                        "type": "list_repositories_error",
                        "message": "Falha ao consultar repositórios de snapshots do OpenSearch.",
                        "stderr": repo_result.stderr.strip(),
                        "stdout": repo_result.stdout.strip(),
                    },
                    "commands": {
                        "list_repositories": self._sanitize_command(repo_command)
                    },
                },
                "collected_at": self._to_iso_utc(datetime.now(timezone.utc)),
            }

        try:
            repos_payload = json.loads(repo_result.stdout or "{}")
        except json.JSONDecodeError:
            return {
                "status": "partial",
                "source": "opensearch_snapshot_api",
                "domain_status": domain_status,
                "domain_error": domain_error,
                "snapshot_api": {
                    "error": {
                        "type": "list_repositories_invalid_json",
                        "message": "Resposta inválida na listagem de repositórios do OpenSearch.",
                    },
                    "commands": {
                        "list_repositories": self._sanitize_command(repo_command)
                    },
                },
                "collected_at": self._to_iso_utc(datetime.now(timezone.utc)),
            }

        repositories = list(repos_payload.keys()) if isinstance(repos_payload, dict) else []
        preferred_repo = os.getenv("OPENSEARCH_SNAPSHOT_REPOSITORY", "").strip()

        selected_repo = None
        if preferred_repo and preferred_repo in repositories:
            selected_repo = preferred_repo
        elif "cs-automated-enc" in repositories:
            selected_repo = "cs-automated-enc"
        elif "cs-automated" in repositories:
            selected_repo = "cs-automated"
        elif repositories:
            selected_repo = repositories[0]

        if not selected_repo:
            return {
                "status": "partial",
                "source": "opensearch_snapshot_api",
                "domain_status": domain_status,
                "domain_error": domain_error,
                "snapshot_api": {
                    "repositories": repositories,
                    "error": {
                        "type": "no_snapshot_repository_found",
                        "message": "Nenhum repositório de snapshot foi encontrado no domínio.",
                    },
                    "commands": {
                        "list_repositories": self._sanitize_command(repo_command)
                    },
                },
                "collected_at": self._to_iso_utc(datetime.now(timezone.utc)),
            }

        snapshots_url = f"{endpoint_url}/_snapshot/{quote(selected_repo, safe='')}/_all"
        snapshots_command = self._build_sigv4_curl_command(snapshots_url)
        if snapshots_command is None:
            return {
                "status": "partial",
                "source": "opensearch_snapshot_api",
                "domain_status": domain_status,
                "domain_error": domain_error,
                "snapshot_api": {
                    "repositories": repositories,
                    "selected_repository": selected_repo,
                    "error": {
                        "type": "missing_sigv4_credentials",
                        "message": (
                            "Não foi possível obter credenciais AWS para consulta da API de "
                            "snapshots com assinatura SigV4."
                        ),
                    },
                    "commands": {
                        "list_repositories": self._sanitize_command(repo_command),
                    },
                },
                "collected_at": self._to_iso_utc(datetime.now(timezone.utc)),
            }

        snapshots_result = self._run_command(snapshots_command)
        if snapshots_result is None:
            return {
                "status": "partial",
                "source": "opensearch_snapshot_api",
                "domain_status": domain_status,
                "domain_error": domain_error,
                "snapshot_api": {
                    "repositories": repositories,
                    "selected_repository": selected_repo,
                    "error": {
                        "type": "curl_not_found",
                        "message": "Comando curl não encontrado para consulta de snapshots.",
                    },
                    "commands": {
                        "list_repositories": self._sanitize_command(repo_command),
                        "list_snapshots": self._sanitize_command(snapshots_command),
                    },
                },
                "collected_at": self._to_iso_utc(datetime.now(timezone.utc)),
            }

        if snapshots_result.returncode != 0:
            return {
                "status": "partial",
                "source": "opensearch_snapshot_api",
                "domain_status": domain_status,
                "domain_error": domain_error,
                "snapshot_api": {
                    "repositories": repositories,
                    "selected_repository": selected_repo,
                    "error": {
                        "type": "list_snapshots_error",
                        "message": "Falha ao consultar snapshots do repositório selecionado.",
                        "stderr": snapshots_result.stderr.strip(),
                        "stdout": snapshots_result.stdout.strip(),
                    },
                    "commands": {
                        "list_repositories": self._sanitize_command(repo_command),
                        "list_snapshots": self._sanitize_command(snapshots_command),
                    },
                },
                "collected_at": self._to_iso_utc(datetime.now(timezone.utc)),
            }

        try:
            snapshots_payload = json.loads(snapshots_result.stdout or "{}")
        except json.JSONDecodeError:
            return {
                "status": "partial",
                "source": "opensearch_snapshot_api",
                "domain_status": domain_status,
                "domain_error": domain_error,
                "snapshot_api": {
                    "repositories": repositories,
                    "selected_repository": selected_repo,
                    "error": {
                        "type": "list_snapshots_invalid_json",
                        "message": "Resposta inválida na listagem de snapshots.",
                    },
                    "commands": {
                        "list_repositories": self._sanitize_command(repo_command),
                        "list_snapshots": self._sanitize_command(snapshots_command),
                    },
                },
                "collected_at": self._to_iso_utc(datetime.now(timezone.utc)),
            }

        snapshots = snapshots_payload.get("snapshots", [])
        if not isinstance(snapshots, list):
            snapshots = []

        latest_snapshot = None
        if snapshots:
            latest_snapshot = sorted(
                snapshots,
                key=lambda item: item.get("start_time_in_millis") or 0,
                reverse=True,
            )[0]

        return {
            "status": "collected",
            "source": "opensearch_snapshot_api",
            "domain_status": domain_status,
            "domain_error": domain_error,
            "snapshot_api": {
                "repositories": repositories,
                "selected_repository": selected_repo,
                "snapshots_found": len(snapshots),
                "latest_snapshot": {
                    "snapshot": latest_snapshot.get("snapshot") if latest_snapshot else None,
                    "state": latest_snapshot.get("state") if latest_snapshot else None,
                    "start_time": latest_snapshot.get("start_time") if latest_snapshot else None,
                    "end_time": latest_snapshot.get("end_time") if latest_snapshot else None,
                    "start_time_in_millis": (
                        latest_snapshot.get("start_time_in_millis") if latest_snapshot else None
                    ),
                    "end_time_in_millis": (
                        latest_snapshot.get("end_time_in_millis") if latest_snapshot else None
                    ),
                    "indices_count": (
                        len(latest_snapshot.get("indices", []))
                        if latest_snapshot and isinstance(latest_snapshot.get("indices"), list)
                        else None
                    ),
                    "indices": (
                        sorted(latest_snapshot.get("indices", []))
                        if latest_snapshot and isinstance(latest_snapshot.get("indices"), list)
                        else None
                    ),
                },
                "sample_snapshots": snapshots[: self.max_recovery_points],
            },
            "commands": {
                "describe_domain": " ".join(describe_command),
                "list_repositories": self._sanitize_command(repo_command),
                "list_snapshots": self._sanitize_command(snapshots_command),
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

            latest_snapshot = (
                snapshot_evidence.get("snapshot_api", {}).get("latest_snapshot")
                if isinstance(snapshot_evidence, dict)
                else None
            )

            latest_backup = None
            if isinstance(latest_snapshot, dict) and latest_snapshot.get("snapshot"):
                latest_backup = {
                    "source": "opensearch_snapshot_api",
                    "repository": snapshot_evidence.get("snapshot_api", {}).get(
                        "selected_repository"
                    ),
                    "snapshot": latest_snapshot.get("snapshot"),
                    "state": latest_snapshot.get("state"),
                    "start_time": latest_snapshot.get("start_time"),
                    "end_time": latest_snapshot.get("end_time"),
                }

            return {
                "resource_type": resource.resource_type,
                "resource_arn": resource.resource_arn,
                "collected_at": collected_at,
                "status": "ok" if latest_backup else "partial",
                "backup_service": "opensearch_managed_snapshots",
                "collection_strategy": "opensearch_snapshot_api_sigv4",
                "latest_backup": latest_backup,
                "alternative_snapshot_evidence": snapshot_evidence,
                "note": (
                    "Evidências coletadas via API de snapshots do OpenSearch com assinatura SigV4."
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
    opensearch_resource_arn = os.getenv("OPENSEARCH_RESOURCE_ARN", "").strip()
    if not opensearch_resource_arn:
        return []

    return [
        BackupResource(
            resource_type="opensearch",
            resource_arn=opensearch_resource_arn,
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

    if not resources:
        parser.error(
            "Nenhum recurso configurado. Defina OPENSEARCH_RESOURCE_ARN ou use --add-resource."
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
