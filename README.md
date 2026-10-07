# Scope.Glacier — Energy Markets Intelligence Platform

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![AWS](https://img.shields.io/badge/AWS-Native-orange.svg)](https://aws.amazon.com/)
[![Tests](https://img.shields.io/badge/tests-64%20passing-brightgreen.svg)](tests/)

## Overview

**Scope.Glacier** is an energy markets intelligence platform built on AWS native services. It ingests spot prices and supply/demand data from the US EIA Open Data API, supplementary pricing from AlphaVantage and FRED, and uses Amazon Bedrock (Amazon Nova Lite) to generate composite energy signals, supply/demand balance analysis, infrastructure disruption monitoring, and AI-powered price outlooks across crude oil, natural gas, gasoline, and heating oil.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  EIA Open    │  │ AlphaVantage │  │  FRED Economic Data  │  │
│  │  Data API    │  │  (Prices)    │  │  (Macro Indicators)  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
└─────────┼─────────────────┼─────────────────────┼──────────────┘
          │                 │                     │
          ▼                 ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AWS LAMBDA (INGESTION)                        │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  eia_ingestion_handler.py — EventBridge Scheduled Trigger   │ │
│  │  - Fetches EIA spot prices for tracked commodities         │ │
│  │  - Pulls supplementary prices from AlphaVantage / FRED     │ │
│  │  - Writes raw data to S3                                   │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DATA LAKE (S3 + ICEBERG)                      │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ price_series │  │  supply_     │  │   energy_commodities   │ │
│  │ (daily OHLC)│  │  demand_bal. │  │   (reference data)     │ │
│  ├─────────────┤  ├──────────────┤  ├────────────────────────┤ │
│  │  pipelines   │  │  refineries  │  │   glacier_signals      │ │
│  │  (infra)    │  │  (capacity)  │  │   (output signals)     │ │
│  └─────────────┘  └──────────────┘  └────────────────────────┘ │
└─────────┬──────────────────┬──────────────────┬─────────────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                  AWS GLUE ETL PIPELINE                           │
│  ┌───────────────┐  ┌────────────────┐  ┌──────────────────┐   │
│  │  energy_price │  │  supply_       │  │  infrastructure  │   │
│  │  _etl.py      │  │  demand_etl.py │  │  _etl.py          │   │
│  │  - Spot stats │  │  - Implied bal │  │  - Pipeline util  │   │
│  │  - Volatility │  │  - Inv. cover  │  │  - Refinery out   │   │
│  │  - Returns    │  │  - Drawdown    │  │  - Disruption det │   │
│  └───────────────┘  └────────────────┘  └──────────────────┘   │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              STEP FUNCTIONS (ANALYSIS ORCHESTRATION)             │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  1. Ingest EIA Price Data                                  │ │
│  │  2. Compute Glacier Scores (GlacierIntelligenceService)     │ │
│  │  3. Generate AI Outlook (Bedrock Converse API)              │ │
│  │  4. Write Signals to Iceberg Tables                        │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                 AMAZON ATHENA (QUERY ENGINE)                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │  energy_price    │  │  supply_demand   │  │  infrastruct- │  │
│  │  _dashboard.sql  │  │  _fundamentals   │  │  ure_disrupt- │  │
│  │  - Multi-comm    │  │  .sql            │  │  ion.sql      │  │
│  │    compare       │  │  - Implied bal   │  │  - Pipeline   │  │
│  │  - Vol & return  │  │  - Inv. days    │  │    status     │  │
│  │  - Moving avg    │  │  - 4W avg delta │  │  - Refinery   │  │
│  └──────────────────┘  └──────────────────┘  │    offline    │  │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│               INTELLIGENCE LAYER (BEDROCK AI)                    │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Amazon Nova Lite via Converse API                         │ │
│  │  - Composite Glacier Signal Generation                     │ │
│  │  - Supply/Demand Narrative Analysis                        │ │
│  │  - Geopolitical Risk Assessment                            │ │
│  │  - Seasonal Pattern & Price Outlook                        │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Key Features

- **EIA Open Data Integration**: Spot prices, petroleum supply/demand, inventory, production
- **Apache Iceberg Tables**: ACID-compliant table format on S3 with time-travel queries
- **Glacier Signal Engine**: Composite score (Supply/Demand 30% + Price Momentum 25% + Geopolitical 25% + Seasonal 20%)
- **Supply/Demand Analysis**: Implied balance, inventory coverage days, spare capacity, drawdown risk
- **Infrastructure Monitoring**: Pipeline utilization and disruption tracking, refinery offline capacity
- **AI-Powered Outlook**: Amazon Nova Lite (`us.amazon.nova-lite-v1:0` in us-east-1) generates narrative price direction analysis via the Bedrock Converse API. Anthropic model ids are rejected because Claude on Bedrock is Marketplace-billed and is not covered by AWS promo credits.
- **Volatility Computation**: Annualized rolling volatility with moving averages
- **Athena Views**: Pre-built analytical views for price dashboard, S/D fundamentals, and disruption monitor

## Prerequisites

- Python 3.10+
- AWS account with Amazon Bedrock access enabled for Amazon Nova Lite (`us.amazon.nova-lite-v1:0`)
- US EIA API key (free at https://www.eia.gov/opendata/)
- AWS credentials configured (via `.env` or IAM)
- Terraform 1.5+ (for infrastructure deployment)

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your AWS credentials, EIA key, and API keys
```

### 3. Deploy Infrastructure

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

### 4. Run Tests

```bash
python -m pytest tests/ -v
```

## Project Structure

```
scope-glacier/
├── bedrock_client.py           # Bedrock Converse API wrapper
├── requirements.txt            # Python dependencies
├── src/
│   ├── models/                 # Domain models (6)
│   │   ├── energy_commodity.py #   Commodity reference (WTI, Brent, HH)
│   │   ├── price_series.py     #   Time series with volatility/moving avg
│   │   ├── supply_demand.py    #   Production, consumption, inventory
│   │   ├── refinery.py         #   Refinery capacity & utilization
│   │   ├── pipeline.py         #   Pipeline flow & disruption status
│   │   └── glacier_signal.py   #   Composite signal output
│   ├── services/               # Business logic (3)
│   │   ├── eia_service.py      #   EIA Open Data API client
│   │   ├── pricing_service.py  #   AlphaVantage + FRED energy prices
│   │   └── glacier_intelligence.py #  Composite signal engine
│   ├── aws/                    # AWS integrations
│   │   ├── glue_scripts/       #   ETL scripts (3)
│   │   └── athena_views/       #   SQL views (3)
│   └── lambda/                 #   Lambda handlers (2)
├── terraform/                  #   Infrastructure as Code
└── tests/                      #   Test suite (64 tests)
```

## Tracked Energy Commodities

| Code   | Commodity                  | Unit         | EIA Series ID                        |
|--------|----------------------------|--------------|--------------------------------------|
| WTI    | West Texas Intermediate    | USD/barrel   | PET.RWTC.D                           |
| BRENT  | Brent Crude                | USD/barrel   | PET.RBRTE.D                          |
| HH     | Henry Hub Natural Gas      | USD/MMBtu    | NG.RNGWHHD.D                         |
| RBOB   | RBOB Gasoline              | USD/gallon   | PET.EER_EPMRU_PF4_YCG_DPG.D         |
| HO     | No. 2 Heating Oil          | USD/gallon   | PET.EER_EPD2F_PF4_Yhou_DPG.D        |

## Glacier Signal Formula

```
Composite Score = (
    Supply/Demand Score (utilization, inventory)  x 0.30 +
    Price Momentum Score (returns, volatility)     x 0.25 +
    Geopolitical Score (risk, OPEC compliance)     x 0.25 +
    Seasonal Score (driving, heating season)       x 0.20
)
```

| Score Range | Rating       | Action           |
|-------------|--------------|------------------|
| 80 - 100    | Strong Buy   | Aggressive Long  |
| 65 - 79     | Buy          | Accumulate       |
| 35 - 64     | Hold         | Maintain         |
| 20 - 34     | Sell         | Reduce           |
| 0 - 19      | Strong Sell  | Exit / Short     |

## API Usage

### EIAService — Spot Prices

```python
from src.services.eia_service import EIAService

svc = EIAService()
prices = svc.get_spot_prices("PET.RWTC.D", days=30)
print(f"Latest WTI: ${prices.latest_price}")
print(f"30d Return: {prices.get_return_pct(30)}%")
print(f"Annualized Vol: {prices.get_volatility()}%")
```

### GlacierIntelligenceService — Signal Generation

```python
from src.services.glacier_intelligence import GlacierIntelligenceService

svc = GlacierIntelligenceService()
signal = svc.generate_signal(
    commodity_code="WTI",
    utilization_pct=92.0,
    inventory_days=28.0,
    geopolitical_risk=65.0,
    opec_compliance=85.0,
    is_driving_season=True,
)
print(f"WTI: {signal.glacier_score}/100 ({signal.signal_rating.value})")
```

### EnergyPricingService — Multi-Source Prices

```python
from src.services.pricing_service import EnergyPricingService

svc = EnergyPricingService()
prices = svc.get_all_prices()
print(f"WTI: ${prices.get('WTI')}, Brent: ${prices.get('BRENT')}, NG: ${prices.get('NG')}")
```

## Infrastructure Monitoring

### Pipeline Tracking

```python
from src.models.pipeline import Pipeline, PipelineStatus

pipe = Pipeline(
    name="Colonial Pipeline",
    commodity="Crude Oil",
    origin="Houston, TX",
    destination="New York Harbor",
    capacity_bpd=2_500_000,
    current_flow_bpd=2_100_000,
    status=PipelineStatus.OPERATIONAL,
)
print(f"Utilization: {pipe.utilization_pct}%")
print(f"Disrupted: {pipe.is_disrupted}")
```

### Refinery Tracking

```python
from src.models.refinery import Refinery, RefineryStatus

ref = Refinery(
    name="Baytown",
    region="Gulf Coast",
    country="United States",
    capacity_bpd=560_000,
    utilization_pct=88.0,
    status=RefineryStatus.OPERATING,
    crude_type="Light Sweet",
)
print(f"Throughput: {ref.throughput_bpd:,.0f} bpd")
print(f"Offline: {ref.offline_bpd:,.0f} bpd")
```

## AWS Cost Estimates (Monthly)

| Service             | Usage                          | Est. Cost   |
|---------------------|--------------------------------|-------------|
| S3 Storage          | 50 GB Iceberg tables           | ~$1.20      |
| Athena Queries      | 100 queries/month              | ~$5.00      |
| Lambda              | 10K invocations                | ~$0.50      |
| Step Functions      | 500 state transitions          | ~$0.75      |
| Glue ETL            | 3 jobs x 10 min                | ~$1.50      |
| Bedrock (Nova Lite) | 100K tokens/month              | ~$0.02      |
| EventBridge         | 30 scheduled rules             | ~$0.30      |
| **Total**           |                                | **~$9.30**  |

Nova Lite on-demand pricing in us-east-1 is $0.06 per 1M input tokens and $0.24 per 1M output tokens, so 100K tokens is about $0.02.

## License

MIT

---

## CHP Governance

This repository is hardened with the [Consensus Hardening Protocol (CHP)](https://codeberg.org/cubiczan/consensus-hardening-protocol), Cubiczan's decision-governance layer for multi-agent AI systems.

### Protocol Layers
- **R0 Gate**: All decisions must pass Solvable, Scoped, Valid, Worth_it checks
- **Foundation Disclosure**: 1-3 weakest assumptions, 1-2 invalidation conditions, 1 key vulnerability
- **Adversarial Layer**: Mandatory devil's advocate at Phase 0 and Round 3
- **State Machine**: EXPLORING → PROVISIONAL → PROVISIONAL_LOCK → LOCKED
- **Third-Party Validation**: Independent CONFIRM/REJECT before lock

### Domain Configuration
- **Category**: Mining / Supply Chain
- **Foundation Threshold**: 75
- **CFO Accuracy Guard**: Disabled

### Compliance Artifacts
| File | Purpose |
|------|---------|
| `.chp/STATE_MACHINE.md` | Decision state transitions |
| `.chp/R0_CONFIG.yaml` | Domain-calibrated thresholds |
| `.chp/ADVERSARIAL_PROMPTS.md` | Standardized challenge templates |
| `.chp/CHP_COMPLIANCE.md` | Compliance tracking & audit trail |

### CHP Version
cognitive-mesh-orchestrator 0.1.0 | [Protocol Docs](https://codeberg.org/cubiczan/consensus-hardening-protocol)


## Demo

[![Demo Video](https://img.shields.io/badge/Watch_Demo-3min-blue)](docs/media/scope-glacier-demo.mp4)

