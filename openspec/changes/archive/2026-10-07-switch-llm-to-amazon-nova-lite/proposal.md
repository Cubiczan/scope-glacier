# Proposal

## Why

The account's AWS promo credits do not cover Anthropic Claude on Amazon Bedrock: Claude is sold through AWS Marketplace and is IAM-denied, so the current default model cannot be called. Amazon Nova is credit-eligible and is already invocable through the Bedrock Converse API.

## What Changes

- **BREAKING**: The default Bedrock model changes from `anthropic.claude-3-haiku-20240307-v1:0` to the US Amazon Nova Lite inference profile `us.amazon.nova-lite-v1:0` in us-east-1.
- Energy-market analysis keeps using the Bedrock Converse API, with a provider-neutral request and response shape.
- Model id overrides that name an Anthropic model (`anthropic.*` and cross-region ids such as `us.anthropic.*`) are rejected with a clear error in the client, the analysis Lambda, and Terraform variable validation.
- Lambda IAM allows `bedrock:Converse` only for `foundation-model/amazon.nova-*` and `inference-profile/us.amazon.nova-*`, and no longer grants Bedrock on `*`.
- `.env.example`, README, a repository verify script, and tests match the Nova Lite default.

## Capabilities

### New Capabilities

- `bedrock-energy-analysis`: Select an Amazon Nova model and generate energy-market narrative analysis through the Bedrock Converse API, refusing Anthropic model overrides.

### Modified Capabilities

- None. This repository has no existing specs.

## Impact

- `bedrock_client.py`, `src/lambda/glacier_analysis_handler.py`, and `src/services/glacier_intelligence.py` (analysis path uses the shared client).
- `terraform/variables.tf` and the Lambda IAM policy in `terraform/main.tf`.
- `.env.example`, `README.md`, `scripts/verify_bedrock_model.py`, and tests.
- Operators who set `BEDROCK_MODEL_ID` to a Claude id must switch to a Nova id. Other Nova model ids remain allowed.
