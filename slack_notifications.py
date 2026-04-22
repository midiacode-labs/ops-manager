import os
import argparse
from datetime import datetime, timezone

import requests
from requests.exceptions import RequestException
from dotenv import load_dotenv


load_dotenv()


def send_slack_deploy_notification(action, source, status_code):
    webhook_url = os.getenv("SLACK_DEPLOY_WEBHOOK_URL")
    if not webhook_url:
        return False, "SLACK_DEPLOY_WEBHOOK_URL não configurada"

    environment_name = os.getenv("DEPLOY_ENVIRONMENT_NAME", "development")
    application_name = os.getenv("SLACK_DEPLOY_APP_NAME", "Midiacode Ops Manager")
    status_label = "✅ sucesso" if status_code == 200 else "❌ falha"

    _action_lower = action.lower()
    if any(kw in _action_lower for kw in ("inici", "start", "up", "liga")):
        action_emoji = "🟢"
    elif any(kw in _action_lower for kw in ("par", "stop", "down", "deslig")):
        action_emoji = "🔴"
    else:
        action_emoji = "🔵"

    message = {
        "text": (
            f"[{application_name}] Ambiente {environment_name} {action} via {source}. "
            f"Resultado: {status_label} (status code: {status_code})."
        ),
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{action_emoji} Ambiente de Sandbox: {action}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"📦 *Aplicação:*\n{application_name}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"🌐 *Ambiente:*\n{environment_name}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"⚙️ *Ação:*\n{action}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"🔗 *Origem:*\n{source}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"⚡ *Status:*\n{status_label}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": (
                            "🕐 *Horário UTC*\n"
                            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}"
                        ),
                    },
                ],
            },

        ],
    }

    try:
        response = requests.post(webhook_url, json=message, timeout=10)
        response.raise_for_status()
    except RequestException as exc:
        return False, str(exc)

    return True, None


def parse_args():
    parser = argparse.ArgumentParser(
        description="Envia uma notificação de teste para o webhook do Slack."
    )
    parser.add_argument(
        "--action",
        default="teste-manual",
        help="Ação exibida na notificação.",
    )
    parser.add_argument(
        "--source",
        default="cli",
        help="Origem exibida na notificação.",
    )
    parser.add_argument(
        "--status-code",
        type=int,
        default=200,
        help="Status code exibido na notificação.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    success, error = send_slack_deploy_notification(
        action=args.action,
        source=args.source,
        status_code=args.status_code,
    )

    if success:
        print("Slack notification sent successfully.")
        return 0

    print(f"Failed to send Slack notification: {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())