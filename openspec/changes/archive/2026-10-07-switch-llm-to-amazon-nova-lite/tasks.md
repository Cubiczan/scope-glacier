# Tasks

## 1. Model resolution

- [x] 1.1 Add shared resolution in `bedrock_client.py` that defaults a blank model id to `us.amazon.nova-lite-v1:0`, rejects Anthropic ids (prefix `anthropic.` and a provider segment `anthropic`) with an error that names Nova Lite, and keeps Converse request/response handling. Verify with unit tests for the default, a Nova override, both Anthropic forms, and a mocked Converse call.
- [x] 1.2 Use that resolver in `src/lambda/glacier_analysis_handler.py` before `converse`, outside the analysis-unavailable catch. Verify a handler test that an Anthropic env value raises and that an unset id calls Converse with `us.amazon.nova-lite-v1:0`.

## 2. Infrastructure and configuration

- [x] 2.1 Default `bedrock_model_id` to `us.amazon.nova-lite-v1:0` and reject Anthropic ids in `terraform/variables.tf`. Move Bedrock actions off `Resource = "*"` onto `foundation-model/amazon.nova-*` and `inference-profile/us.amazon.nova-*` in `terraform/main.tf`. Verify the policy JSON contains those patterns and does not grant `bedrock:Converse` on `*`.
- [x] 2.2 Set `BEDROCK_MODEL_ID=us.amazon.nova-lite-v1:0` in `.env.example` and describe Amazon Nova Lite (Converse API, us-east-1, updated token cost) in `README.md`. Verify neither file still names Claude Haiku as the model in use.

## 3. Verification

- [x] 3.1 Add `scripts/verify_bedrock_model.py` that fails when a production default or the IAM policy still selects Claude or omits the Nova resource patterns, and invoke it from tests. Verify `pytest` and the script both exit 0.
