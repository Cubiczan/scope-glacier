# Design

## Context

See proposal.md for why Claude cannot stay the default. Today `bedrock_client.py` and `src/lambda/glacier_analysis_handler.py` already call `bedrock-runtime` `converse`, but both default `modelId` to `anthropic.claude-3-haiku-20240307-v1:0`. The same string is the Terraform variable default and the `.env.example` value. The Lambda IAM statement grants `bedrock:Converse` on `Resource = "*"`, so it does not distinguish Nova from Anthropic. There is no verify script in the repository.

## Goals / Non-Goals

**Goals:**

- One shared model-id resolution used by the client and the analysis Lambda.
- Converse remains the only invocation API.
- Anthropic ids fail closed in application code and in Terraform validation.
- IAM is limited to Nova foundation models and US Nova inference profiles.
- A local verify script fails if a production default still names Claude.

**Non-Goals:**

- Changing score formulas, Athena SQL, or the analysis prompt text beyond the model that writes it.
- Adding streaming (`ConverseStream`) or other model families.
- Calling Bedrock from tests.

## Decisions

### 1. Shared resolver in `bedrock_client.py`

`resolve_bedrock_model_id()` returns the stripped id, or `us.amazon.nova-lite-v1:0` when the value is missing or blank. It raises `AnthropicModelError` (a `ValueError`) when the id starts with `anthropic.` or any dot-separated segment equals `anthropic` (covers `us.anthropic.*`, `eu.anthropic.*`, and `global.anthropic.*`). Comparison is case-insensitive.

The Lambda calls this helper before `converse`, outside the handler's "analysis unavailable" catch, so a rejected override is an error rather than a narrative fallback.

Alternative considered: duplicate the check in the Lambda. Rejected because the two call sites already drifted once on the default string.

### 2. Keep the Converse message shape

Requests stay `{modelId, messages: [{role, content: [{text}]}], system: [{text}], inferenceConfig: {maxTokens, temperature}}`. Responses stay the Converse `output.message.content[].text` join. No Anthropic `invoke_model` body is introduced.

### 3. IAM resources

Remove `bedrock:Converse` from the existing `Resource = "*"` statement. Add a statement that allows `bedrock:Converse` and `bedrock:InvokeModel` (AWS authorizes Converse through `InvokeModel`) plus `bedrock:GetInferenceProfile` (required to use an inference profile) on:

- `arn:aws:bedrock:*::foundation-model/amazon.nova-*` — region wildcard because the US geo profile routes to us-east-1, us-east-2, and us-west-2
- `arn:aws:bedrock:${var.aws_region}:${account}:inference-profile/us.amazon.nova-*`

`aws_caller_identity` supplies the account id. No Anthropic ARN appears in the policy.

Alternative considered: an explicit Deny on `anthropic.*`. The scoped Allow already excludes Anthropic, and a Deny would fight a later intentional exception. Validation in code and Terraform covers operator overrides.

### 4. Terraform validation

`bedrock_model_id` defaults to `us.amazon.nova-lite-v1:0`. A `validation` block rejects ids that start with `anthropic.` or contain `.anthropic.`, matching the runtime rule. `startswith` and `strcontains` are available under the module's Terraform `>= 1.5.0` constraint.

### 5. Verify script

`scripts/verify_bedrock_model.py` scans the production defaults (client, Lambda, Terraform variable, `.env.example`, README) and the IAM policy. It exits non-zero if `anthropic.claude` is still a default or if the Nova resource patterns are missing. Tests import the same checks so `pytest` covers them. The repository had no verify script; this adds the one the model switch needs.

### 6. Docs and cost

README names Amazon Nova Lite via the Converse API. The cost row uses published us-east-1 on-demand rates of $0.06 per 1M input tokens and $0.24 per 1M output tokens. At 100K tokens/month the line is about $0.02, and the monthly total is about $9.27.

## Risks / Trade-offs

- [US inference profile routes outside us-east-1] → IAM uses a region wildcard only on `amazon.nova-*` foundation models, which is the destination set for `us.amazon.nova-lite-v1:0`.
- [A future global Nova profile id would not match `us.amazon.nova-*`] → Operators can widen the inference-profile resource later; the default profile is the US one the account should call.
- [Terraform validation cannot import the Python helper] → The HCL condition mirrors the same two Anthropic patterns and is asserted by the verify script reading `variables.tf`.

## Migration Plan

1. Deploy the Lambda code and IAM policy together so the new model id is allowed when the environment variable flips.
2. Leave `BEDROCK_MODEL_ID` unset to pick up the Nova Lite default, or set it to `us.amazon.nova-lite-v1:0`.
3. Rollback is reverting the default string and restoring `bedrock:Converse` on `*`. Do not roll the code back without restoring IAM, or Nova calls fail closed.

## Open Questions

None. The target model id, region, Converse API, IAM resource patterns, and Anthropic rejection behavior are specified by the request.
