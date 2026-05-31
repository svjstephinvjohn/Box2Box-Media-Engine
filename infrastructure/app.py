#!/usr/bin/env python3
"""
AWS CDK App entry point for Football App serverless infrastructure.

Deploys the following stacks in order:
  1. SecretsStack   — Secrets Manager secrets (OpenAI, Meta, API-Football)
  2. StorageStack   — DynamoDB tables + S3 bucket
  3. LambdaStack    — All Lambda functions + shared layer
  4. StepFunctionStack — Step Functions Express Workflow
  5. EventBridgeStack  — EventBridge schedules

Usage:
  pip install -r infrastructure/requirements.txt
  cdk bootstrap aws://ACCOUNT_ID/us-east-1
  cdk deploy --all
"""
import aws_cdk as cdk
from stacks.secrets_stack import SecretsStack
from stacks.storage_stack import StorageStack
from stacks.lambda_stack import LambdaStack
from stacks.step_functions_stack import StepFunctionsStack
from stacks.eventbridge_stack import EventBridgeStack

app = cdk.App()

env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "us-east-1",
)

secrets_stack = SecretsStack(app, "FootballAppSecrets", env=env)
storage_stack = StorageStack(app, "FootballAppStorage", env=env)

lambda_stack = LambdaStack(
    app,
    "FootballAppLambdas",
    secrets_stack=secrets_stack,
    storage_stack=storage_stack,
    env=env,
)

sfn_stack = StepFunctionsStack(
    app,
    "FootballAppStepFunctions",
    lambda_stack=lambda_stack,
    env=env,
)

EventBridgeStack(
    app,
    "FootballAppEventBridge",
    lambda_stack=lambda_stack,
    sfn_stack=sfn_stack,
    env=env,
)

app.synth()
