# bedrock-energy-analysis Specification

## Purpose

Generate narrative energy-market analysis by calling Amazon Bedrock with an Amazon Nova model, and refuse Anthropic Claude model selections that promo credits cannot pay for.

## Requirements

### Requirement: Default model is Amazon Nova Lite

When no model id is configured, energy-market analysis MUST call Amazon Bedrock with the US inference profile `us.amazon.nova-lite-v1:0` in region `us-east-1`. No runtime default, Terraform default, or example environment file MAY name an Anthropic Claude model.

#### Scenario: Unset model id

- **WHEN** `BEDROCK_MODEL_ID` is unset or blank
- **THEN** the analysis request uses model id `us.amazon.nova-lite-v1:0`

#### Scenario: Published defaults

- **WHEN** the Terraform variable default and `.env.example` are read
- **THEN** both set the model id to `us.amazon.nova-lite-v1:0`

### Requirement: Analysis uses the Bedrock Converse API

Energy-market analysis MUST send the prompt through the Bedrock Converse API and MUST read the assistant text from the Converse response. The request MUST NOT use an Anthropic-specific invoke body.

#### Scenario: Successful analysis

- **WHEN** analysis is requested for a commodity signal and Bedrock accepts the call
- **THEN** the caller receives the concatenated assistant text from the Converse output message

#### Scenario: Bedrock failure

- **WHEN** Bedrock returns a retryable or terminal invocation error after the model id has been accepted
- **THEN** the analysis result reports that analysis is unavailable and includes the error text

### Requirement: Anthropic model overrides are rejected

The system MUST reject a configured or passed model id that selects Anthropic, including ids that start with `anthropic.` and cross-region inference profile ids whose provider segment is `anthropic` (for example `us.anthropic.*`). The error MUST state that Anthropic Claude is not allowed and MUST name `us.amazon.nova-lite-v1:0` as an allowed alternative. The rejection MUST happen before any Bedrock invocation.

#### Scenario: On-demand Claude id

- **WHEN** the model id is `anthropic.claude-3-haiku-20240307-v1:0`
- **THEN** analysis raises an error that names Anthropic and `us.amazon.nova-lite-v1:0`, and no Converse call is made

#### Scenario: Cross-region Claude inference profile

- **WHEN** the model id is `us.anthropic.claude-3-haiku-20240307-v1:0`
- **THEN** the same rejection occurs and no Converse call is made

#### Scenario: Terraform Anthropic value

- **WHEN** Terraform is planned with `bedrock_model_id` set to an id that starts with `anthropic.` or contains `.anthropic.`
- **THEN** variable validation fails with an error that Anthropic models are not allowed

### Requirement: Non-Anthropic Nova overrides are accepted

A model id that is not an Anthropic selection MUST be forwarded unchanged as the Converse `modelId`.

#### Scenario: Another Nova model

- **WHEN** the model id is `us.amazon.nova-micro-v1:0`
- **THEN** the Converse request uses `us.amazon.nova-micro-v1:0`

### Requirement: IAM allows Nova and not Anthropic

The Lambda role MUST allow Bedrock Converse for Amazon Nova foundation models matching `amazon.nova-*` and for US Nova inference profiles matching `us.amazon.nova-*`. That permission MUST NOT be granted on all resources, and MUST NOT name an Anthropic foundation model or inference profile.

#### Scenario: Nova resources

- **WHEN** the Lambda IAM policy is rendered
- **THEN** Converse is allowed on `foundation-model/amazon.nova-*` and on `inference-profile/us.amazon.nova-*`

#### Scenario: No blanket Bedrock allow

- **WHEN** the Lambda IAM policy is rendered
- **THEN** `bedrock:Converse` is absent from any statement whose resource is `*`
