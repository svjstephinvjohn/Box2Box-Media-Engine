"""
Storage Stack — DynamoDB tables + S3 bucket.

All DynamoDB tables use PAY_PER_REQUEST billing (free tier: 25 WCU/RCU
per month on provisioned; PAY_PER_REQUEST is better for bursty workloads
and has no idle cost — first 25 million requests/month are included in
the always-free tier).

TTL is enabled on all tables so old data expires automatically, keeping
storage within the 25 GB free tier.
"""
import aws_cdk as cdk
import aws_cdk.aws_dynamodb as dynamodb
import aws_cdk.aws_s3 as s3
from constructs import Construct


class StorageStack(cdk.Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # ── News Articles (RAG knowledge store) ───────────────────────────────
        self.news_articles_table = dynamodb.Table(
            self,
            "NewsArticlesTable",
            table_name="football-news-articles",
            partition_key=dynamodb.Attribute(name="article_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="ingested_at", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires_at",
            removal_policy=cdk.RemovalPolicy.DESTROY,  # safe to destroy in dev
            point_in_time_recovery=False,               # keep costs down
        )
        # GSI: query by source for deduplication
        self.news_articles_table.add_global_secondary_index(
            index_name="source-date-index",
            partition_key=dynamodb.Attribute(name="source_name", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="ingested_at", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.INCLUDE,
            non_key_attributes=["title", "link", "is_breaking", "is_transfer", "is_world_cup"],
        )

        # ── Generated Posts ───────────────────────────────────────────────────
        self.generated_posts_table = dynamodb.Table(
            self,
            "GeneratedPostsTable",
            table_name="football-generated-posts",
            partition_key=dynamodb.Attribute(name="post_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="created_at", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires_at",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            point_in_time_recovery=False,
        )
        # GSI: query pending/published posts by status
        self.generated_posts_table.add_global_secondary_index(
            index_name="status-index",
            partition_key=dynamodb.Attribute(name="status", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="created_at", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.INCLUDE,
            non_key_attributes=["post_type", "caption", "image_s3_key", "approval_mode"],
        )

        # ── Publishing Log ────────────────────────────────────────────────────
        self.publishing_log_table = dynamodb.Table(
            self,
            "PublishingLogTable",
            table_name="football-publishing-log",
            partition_key=dynamodb.Attribute(name="post_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="published_at", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            point_in_time_recovery=False,
        )

        # ── Trends ────────────────────────────────────────────────────────────
        self.trends_table = dynamodb.Table(
            self,
            "TrendsTable",
            table_name="football-trends",
            partition_key=dynamodb.Attribute(name="trend_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="detected_at", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires_at",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            point_in_time_recovery=False,
        )

        # ── S3 Bucket — Generated Images ─────────────────────────────────────
        self.images_bucket = s3.Bucket(
            self,
            "ImagesBucket",
            # Bucket name must be globally unique; suffix with account id
            bucket_name=None,  # let CDK auto-generate a unique name
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            # Private bucket — images accessed via presigned URLs
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="delete-old-posts",
                    expiration=cdk.Duration.days(7),
                    prefix="posts/",
                )
            ],
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "NewsArticlesTableName", value=self.news_articles_table.table_name)
        cdk.CfnOutput(self, "GeneratedPostsTableName", value=self.generated_posts_table.table_name)
        cdk.CfnOutput(self, "PublishingLogTableName", value=self.publishing_log_table.table_name)
        cdk.CfnOutput(self, "TrendsTableName", value=self.trends_table.table_name)
        cdk.CfnOutput(self, "ImagesBucketName", value=self.images_bucket.bucket_name)
