-- External Iceberg catalog over the existing Glue database.
-- The bootstrap and scripts/starrocks_query.py replace the property placeholders
-- from the environment before this statement is sent.
-- This does not create or copy tables. Athena keeps using Glue directly.
-- IRSA / instance-profile variant: docs/STARROCKS.md

CREATE EXTERNAL CATALOG scope_glacier_iceberg
PROPERTIES
(
    "type" = "iceberg",
    "iceberg.catalog.type" = "glue",
    "aws.glue.use_instance_profile" = "false",
    "aws.glue.access_key" = "${AWS_ACCESS_KEY_ID}",
    "aws.glue.secret_key" = "${AWS_SECRET_ACCESS_KEY}",
    "aws.glue.region" = "${AWS_REGION}",
    "aws.s3.use_instance_profile" = "false",
    "aws.s3.access_key" = "${AWS_ACCESS_KEY_ID}",
    "aws.s3.secret_key" = "${AWS_SECRET_ACCESS_KEY}",
    "aws.s3.region" = "${AWS_REGION}"
);
