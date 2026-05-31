"""
Secrets Stack — creates Secrets Manager secrets for all credentials.

NOTE on Free Tier:
  Secrets Manager is NOT on the AWS free tier.
  Cost: $0.40/secret/month × 3 secrets = ~$1.20/month.
  Alternative: use SSM Parameter Store SecureString (free for standard params)
  by setting the SECRETS_BACKEND env var to "ssm" in LambdaStack.
"""
import aws_cdk as cdk
import aws_cdk.aws_secretsmanager as secretsmanager
from constructs import Construct


class SecretsStack(cdk.Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # OpenAI credentials
        self.openai_secret = secretsmanager.Secret(
            self,
            "OpenAISecret",
            secret_name="football-app/openai",
            description="OpenAI API key for Football App",
            # Initial placeholder — populate manually:
            # aws secretsmanager put-secret-value \
            #   --secret-id football-app/openai \
            #   --secret-string '{"api_key": "sk-..."}'
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"api_key": "REPLACE_ME"}',
                generate_string_key="placeholder",
                exclude_punctuation=True,
            ),
        )

        # Meta / Instagram credentials
        self.meta_secret = secretsmanager.Secret(
            self,
            "MetaSecret",
            secret_name="football-app/meta",
            description="Meta Graph API credentials for Football App",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template=(
                    '{"app_id":"REPLACE_ME","app_secret":"REPLACE_ME",'
                    '"access_token":"REPLACE_ME","account_id":"REPLACE_ME"}'
                ),
                generate_string_key="placeholder",
                exclude_punctuation=True,
            ),
        )

        # API-Football key
        self.api_football_secret = secretsmanager.Secret(
            self,
            "APIFootballSecret",
            secret_name="football-app/api-football",
            description="API-Football (RapidAPI) key for Football App",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"api_key": "REPLACE_ME"}',
                generate_string_key="placeholder",
                exclude_punctuation=True,
            ),
        )

        # Outputs for reference
        cdk.CfnOutput(self, "OpenAISecretArn", value=self.openai_secret.secret_arn)
        cdk.CfnOutput(self, "MetaSecretArn", value=self.meta_secret.secret_arn)
        cdk.CfnOutput(self, "APIFootballSecretArn", value=self.api_football_secret.secret_arn)
