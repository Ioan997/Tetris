"""Tera Tetris - Static website hosted on AWS S3 + CloudFront."""

import json
import pulumi
import pulumi_aws as aws

# ---------------------------------------------------------------------------
# S3 bucket (private — content served exclusively through CloudFront)
# ---------------------------------------------------------------------------
bucket = aws.s3.BucketV2("tera-tetris-bucket")

# Block all public access at the bucket level
bucket_public_access_block = aws.s3.BucketPublicAccessBlock(
    "tera-tetris-public-access-block",
    bucket=bucket.id,
    block_public_acls=True,
    block_public_policy=True,
    ignore_public_acls=True,
    restrict_public_buckets=True,
)

# ---------------------------------------------------------------------------
# CloudFront Origin Access Control (OAC) — modern replacement for OAI
# ---------------------------------------------------------------------------
oac = aws.cloudfront.OriginAccessControl(
    "tera-tetris-oac",
    description="OAC for Tera Tetris S3 origin",
    origin_access_control_origin_type="s3",
    signing_behavior="always",
    signing_protocol="sigv4",
)

# ---------------------------------------------------------------------------
# CloudFront distribution
# ---------------------------------------------------------------------------
distribution = aws.cloudfront.Distribution(
    "tera-tetris-distribution",
    origins=[
        aws.cloudfront.DistributionOriginArgs(
            domain_name=bucket.bucket_regional_domain_name,
            origin_id="s3-tera-tetris",
            origin_access_control_id=oac.id,
        )
    ],
    enabled=True,
    default_root_object="index.html",
    # Serve index.html for SPA-style 403/404 responses from S3
    custom_error_responses=[
        aws.cloudfront.DistributionCustomErrorResponseArgs(
            error_code=403,
            response_code=200,
            response_page_path="/index.html",
        ),
        aws.cloudfront.DistributionCustomErrorResponseArgs(
            error_code=404,
            response_code=200,
            response_page_path="/index.html",
        ),
    ],
    default_cache_behavior=aws.cloudfront.DistributionDefaultCacheBehaviorArgs(
        target_origin_id="s3-tera-tetris",
        viewer_protocol_policy="redirect-to-https",
        allowed_methods=["GET", "HEAD", "OPTIONS"],
        cached_methods=["GET", "HEAD"],
        # Managed cache policy: CachingOptimized
        cache_policy_id="658327ea-f89d-4fab-a63d-7e88639e58f6",
        compress=True,
    ),
    price_class="PriceClass_100",  # US, Canada, Europe
    restrictions=aws.cloudfront.DistributionRestrictionsArgs(
        geo_restriction=aws.cloudfront.DistributionRestrictionsGeoRestrictionArgs(
            restriction_type="none",
        )
    ),
    viewer_certificate=aws.cloudfront.DistributionViewerCertificateArgs(
        cloudfront_default_certificate=True,
    ),
)

# ---------------------------------------------------------------------------
# S3 bucket policy — grant CloudFront OAC read access
# ---------------------------------------------------------------------------
bucket_policy = aws.s3.BucketPolicy(
    "tera-tetris-bucket-policy",
    bucket=bucket.id,
    policy=pulumi.Output.all(bucket.arn, distribution.arn).apply(
        lambda args: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "AllowCloudFrontServicePrincipal",
                        "Effect": "Allow",
                        "Principal": {"Service": "cloudfront.amazonaws.com"},
                        "Action": "s3:GetObject",
                        "Resource": f"{args[0]}/*",
                        "Condition": {
                            "StringEquals": {
                                "AWS:SourceArn": args[1],
                            }
                        },
                    }
                ],
            }
        )
    ),
    opts=pulumi.ResourceOptions(depends_on=[bucket_public_access_block]),
)

# ---------------------------------------------------------------------------
# Upload index.html to S3
# ---------------------------------------------------------------------------
index_html = aws.s3.BucketObjectv2(
    "index.html",
    bucket=bucket.id,
    key="index.html",
    source=pulumi.FileAsset("www/index.html"),
    content_type="text/html; charset=utf-8",
    # Short cache TTL so updates propagate quickly
    cache_control="max-age=300",
)

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
pulumi.export("bucket_name", bucket.bucket)
pulumi.export(
    "url",
    distribution.domain_name.apply(lambda d: f"https://{d}"),
)
