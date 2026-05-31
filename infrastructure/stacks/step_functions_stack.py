"""
Step Functions Stack — Express Workflow for the content pipeline.

Uses EXPRESS workflow type because:
  - Runs are short (< 5 minutes)
  - Higher throughput needed
  - Lower cost vs STANDARD ($0.00001/state transition vs $0.000025)
  - AWS Free Tier: 4,000 state transitions/month for EXPRESS workflows
"""
import json
import os
import aws_cdk as cdk
import aws_cdk.aws_stepfunctions as sfn
import aws_cdk.aws_iam as iam
import aws_cdk.aws_logs as logs
from constructs import Construct

from stacks.lambda_stack import LambdaStack

WORKFLOW_DEF_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "step_functions", "workflow.json"
)


class StepFunctionsStack(cdk.Stack):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        lambda_stack: LambdaStack,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        lk = lambda_stack

        # ── CloudWatch log group for the Express workflow ─────────────────────
        log_group = logs.LogGroup(
            self,
            "PipelineLogGroup",
            log_group_name="/football-app/step-functions/content-pipeline",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # ── Load and substitute ARNs into the ASL definition ─────────────────
        with open(WORKFLOW_DEF_PATH) as f:
            definition_str = f.read()

        substitutions = {
            "${ContentSelectionFunctionArn}": lk.content_selection_fn.function_arn,
            "${CaptionGenerationFunctionArn}": lk.caption_generation_fn.function_arn,
            "${ImagePromptFunctionArn}": lk.image_prompt_fn.function_arn,
            "${ImageGenerationFunctionArn}": lk.image_generation_fn.function_arn,
            "${ApprovalNotifierFunctionArn}": lk.approval_notifier_fn.function_arn,
            "${InstagramPublisherFunctionArn}": lk.instagram_publisher_fn.function_arn,
        }
        for placeholder, arn in substitutions.items():
            definition_str = definition_str.replace(placeholder, arn)

        # ── IAM role for the State Machine ───────────────────────────────────
        sfn_role = iam.Role(
            self,
            "StateMachineRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            description="IAM role for Football App content pipeline state machine",
        )

        # Allow invoking all pipeline Lambdas
        for fn in [
            lk.content_selection_fn,
            lk.caption_generation_fn,
            lk.image_prompt_fn,
            lk.image_generation_fn,
            lk.approval_notifier_fn,
            lk.instagram_publisher_fn,
        ]:
            fn.grant_invoke(sfn_role)

        # Allow writing execution logs
        sfn_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogDelivery",
                    "logs:GetLogDelivery",
                    "logs:UpdateLogDelivery",
                    "logs:DeleteLogDelivery",
                    "logs:ListLogDeliveries",
                    "logs:PutLogEvents",
                    "logs:PutResourcePolicy",
                    "logs:DescribeResourcePolicies",
                    "logs:DescribeLogGroups",
                ],
                resources=["*"],
            )
        )

        # ── Create the State Machine ──────────────────────────────────────────
        self.content_pipeline = sfn.CfnStateMachine(
            self,
            "ContentPipeline",
            state_machine_name="football-app-content-pipeline",
            state_machine_type="EXPRESS",
            definition_string=definition_str,
            role_arn=sfn_role.role_arn,
            logging_configuration=sfn.CfnStateMachine.LoggingConfigurationProperty(
                destinations=[
                    sfn.CfnStateMachine.LogDestinationProperty(
                        cloud_watch_logs_log_group=sfn.CfnStateMachine.CloudWatchLogsLogGroupProperty(
                            log_group_arn=log_group.log_group_arn
                        )
                    )
                ],
                include_execution_data=True,
                level="ALL",
            ),
        )

        # ── Pass SFN ARN back to news_ingestion Lambda ────────────────────────
        lk.news_ingestion_fn.add_environment(
            "CONTENT_PIPELINE_SFN_ARN",
            self.content_pipeline.attr_arn,
        )

        cdk.CfnOutput(self, "ContentPipelineArn", value=self.content_pipeline.attr_arn)
        cdk.CfnOutput(self, "PipelineLogGroupName", value=log_group.log_group_name)
