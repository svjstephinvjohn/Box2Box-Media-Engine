"""
EventBridge Stack — schedules for all recurring Lambda triggers.

Schedule summary:
  - Every 30 min  : News ingestion (48 runs/day)
  - Every 45 days : Instagram token refresh

NOTE: EventBridge Scheduler is free for the first 14M invocations/month.
These schedules generate ~1,500 invocations/month — well within free tier.
"""
import aws_cdk as cdk
import aws_cdk.aws_events as events
import aws_cdk.aws_events_targets as targets
import aws_cdk.aws_iam as iam
from constructs import Construct

from stacks.lambda_stack import LambdaStack
from stacks.step_functions_stack import StepFunctionsStack


class EventBridgeStack(cdk.Stack):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        lambda_stack: LambdaStack,
        sfn_stack: StepFunctionsStack,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        lk = lambda_stack

        # ── Rule 1: News ingestion every 30 minutes ───────────────────────────
        news_ingest_rule = events.Rule(
            self,
            "NewsIngestionSchedule",
            rule_name="football-app-news-ingestion",
            description="Trigger news ingestion and embedding every 30 minutes",
            schedule=events.Schedule.rate(cdk.Duration.minutes(30)),
            enabled=True,
        )
        news_ingest_rule.add_target(
            targets.LambdaFunction(
                lk.news_ingestion_fn,
                retry_attempts=2,
                event=events.RuleTargetInput.from_object({"source": "eventbridge-schedule"}),
            )
        )

        # ── Rule 2: Instagram token refresh every 45 days ─────────────────────
        token_refresh_rule = events.Rule(
            self,
            "TokenRefreshSchedule",
            rule_name="football-app-token-refresh",
            description="Refresh Instagram long-lived access token every 45 days",
            schedule=events.Schedule.rate(cdk.Duration.days(45)),
            enabled=True,
        )
        token_refresh_rule.add_target(
            targets.LambdaFunction(
                lk.token_refresh_fn,
                retry_attempts=2,
                event=events.RuleTargetInput.from_object({"source": "eventbridge-schedule"}),
            )
        )

        cdk.CfnOutput(self, "NewsIngestionRuleName", value=news_ingest_rule.rule_name)
        cdk.CfnOutput(self, "TokenRefreshRuleName", value=token_refresh_rule.rule_name)
