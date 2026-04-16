#!/usr/bin/env python3
"""
CLI script to stop the development environment via AWS Lambda.
"""

import boto3
import sys
import json
import os
from dotenv import load_dotenv

from slack_notifications import send_slack_deploy_notification

# Load environment variables
load_dotenv()


def stop_dev_environment():
    """
    Stop the development environment by invoking the AWS Lambda function.
    """
    try:
        lambda_client = boto3.client('lambda', region_name='us-east-1')
        response = lambda_client.invoke(
            FunctionName=(
                'arn:aws:lambda:us-east-1:578416043364:function:'
                'aws-operations-tools-prod-lambda_handler_stop_dev_environment'
            ),
            InvocationType='RequestResponse'
        )
        status_code = response['StatusCode']
        payload = response['Payload'].read().decode() if 'Payload' in response else ''
        return status_code, payload
    except Exception as e:
        print(f"Error stopping dev environment: {str(e)}", file=sys.stderr)
        sys.exit(1)


def main():
    """
    Main function to run the stop dev environment script.
    """
    print("Stopping development environment...")

    status_code, payload = stop_dev_environment()

    slack_sent, slack_error = send_slack_deploy_notification(
        action="parado",
        source="cli",
        status_code=status_code,
        payload=payload,
    )

    if status_code == 200:
        print("✅ Development environment stop request sent successfully!")
        if payload:
            try:
                # Try to parse payload as JSON for better formatting
                payload_data = json.loads(payload)
                print("Response:", json.dumps(payload_data, indent=2))
            except json.JSONDecodeError:
                print("Response:", payload)
        if not slack_sent and os.getenv("SLACK_DEPLOY_WEBHOOK_URL"):
            print(f"Warning: failed to send Slack notification: {slack_error}", file=sys.stderr)
        print("Please wait a few minutes for the environment to be fully stopped.")
    else:
        print(f"❌ Failed to stop development environment. Status code: {status_code}")
        if payload:
            print("Error details:", payload)
        if not slack_sent and os.getenv("SLACK_DEPLOY_WEBHOOK_URL"):
            print(f"Warning: failed to send Slack notification: {slack_error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
