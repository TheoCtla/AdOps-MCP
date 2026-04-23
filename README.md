# AdOps-MCP

A Model Context Protocol (MCP) server that enables AI assistants to read from and act on Google Ads and Meta Ads accounts using natural language. Built for digital advertising agencies managing multiple client accounts.

## Overview

adops-mcp exposes 88 tools across Google Ads and Meta Ads through the MCP protocol, allowing Claude (or any MCP-compatible client) to query performance data, manage campaigns, modify budgets, create ads, and more — all through conversational requests.

The server connects to advertising platforms via their official APIs and translates structured API responses into clean JSON that AI assistants can interpret and act upon.

## Architecture

```
Claude (claude.ai or Claude Code)
    |
    | MCP (stdio or HTTP)
    v
+---------------------------+
| adops-mcp                 |
| (Python, unified server)  |
|                           |
| Google Ads: 50 tools      |
| Meta Ads:   38 tools      |
|                           |
| google-ads Python lib     |
| facebook-business lib     |
+---------------------------+
    |               |
    v               v
  Google Ads      Meta Ads
  (via MCC)       (via BM)
```

Both platforms run in a single server process for local development (stdio transport). For production deployment, they can be separated into two HTTP servers behind a reverse proxy.

## Tools

### Google Ads — Read (24 tools)

| Tool                         |   Description                                                     |
|------------------------------|-------------------------------------------------------------------|
| list_accounts                |   List all client accounts accessible via the MCC                 |
| get_campaign_performance     |   Campaign metrics with cost, conversions, ROAS                   |
| get_adgroup_performance      |   Ad group level performance                                      |
| get_keywords                 |   Keywords with Quality Score breakdown                            |
| get_daily_performance        |   Day-by-day performance over a period                            |
| get_search_terms             |   Actual search queries triggering ads                            |
| get_negative_keywords        |   Existing negative keywords at campaign and ad group level       |
| get_ads                      |   Ads with full RSA copy (headlines, descriptions, pins)          |
| get_geo_performance          |   Performance by geographic location                              |
| get_device_performance       |   Performance by device type                                      |
| get_age_gender_performance   |   Performance by age range and gender                             |
| get_hour_of_day_performance  |   Performance by hour of day                                      |
| get_day_of_week_performance  |   Performance by day of week                                      |
| get_extensions               |   Assets/extensions (sitelinks, callouts, images, etc.)           |
| get_campaign_settings        |   Full campaign configuration (networks, bidding, geo targeting)  |
| get_ad_schedule              |   Ad scheduling configuration                                     |
| get_bid_modifiers            |   Bid adjustments by device, geo, audience, schedule              |
| get_labels                   |   Labels applied to campaigns, ad groups, keywords                |
| get_conversion_actions       |   Configured conversion actions                                   |
| get_auction_insights         |   Competitive landscape data (requires Standard API access)       |
| get_landing_page_performance |   Performance by landing page URL                                 |
| get_audiences                |   Audience segments and their performance                         |
| get_change_history           |   Recent account modification history                             |
| get_budget_info              |   Daily budget vs. current spend with pacing status               |

### Google Ads — Write (26 tools)

| Tool                         |   Description                                                     |
|------------------------------|-------------------------------------------------------------------|
| pause_campaign               |   Pause a campaign                                                |
| enable_campaign              |   Enable a campaign                                               |
| pause_ad_group               |   Pause an ad group                                               |
| enable_ad_group              |   Enable an ad group                                              |
| pause_ad                     |   Pause an ad                                                     |
| enable_ad                    |   Enable an ad                                                    |
| pause_keyword                |   Pause a keyword                                                 |
| enable_keyword               |   Enable a keyword                                                |
| add_negative_keyword         |   Add a negative keyword (campaign or ad group level)             |
| remove_negative_keyword      |   Remove a negative keyword                                       |
| add_keyword                  |   Add a keyword to an ad group                                    |
| remove_keyword               |   Remove a keyword                                                |
| update_keyword_bid           |   Update keyword CPC bid                                          |
| update_campaign_budget       |   Update daily campaign budget                                    |
| update_bid_modifier          |   Update bid adjustment                                           |
| update_ad_schedule           |   Set or replace ad scheduling                                    |
| update_campaign_targeting    |   Modify geographic and language targeting                        |
| create_responsive_search_ad  |   Create a new RSA with headlines, descriptions, and pins         |
| remove_ad                    |   Permanently remove an ad                                        |
| create_sitelink              |   Create a sitelink asset                                         |
| create_callout               |   Create a callout asset                                          |
| add_audience                 |   Add an audience segment to a campaign                           |
| exclude_audience             |   Exclude an audience segment from a campaign                     |
| add_label                    |   Create and apply a label                                        |
| update_tracking_template     |   Update tracking template (account, campaign, or ad group level) |
| update_final_url_suffix      |   Update final URL suffix (UTM parameters)                        |

### Meta Ads — Read (14 tools)

| Tool                         |   Description                                                     |
|------------------------------|-------------------------------------------------------------------|
| list_ad_accounts             |   List all ad accounts via the Business Manager                   |
| get_campaign_performance     |   Campaign metrics with spend, leads, ROAS                        |
| get_adset_performance        |   Ad set level performance                                        |
| get_ad_performance           |   Ad level performance                                            |
| get_audience_breakdown       |   Performance by age, gender, device, placement, region           |
| get_custom_audiences         |   Custom and lookalike audiences                                  |
| get_placement_performance    |   Performance by placement (feed, stories, reels, etc.)           |
| get_hourly_performance       |   Performance by hour of day                                      |
| get_frequency_data           |   Reach and frequency with creative fatigue detection             |
| get_account_info             |   Account details (currency, timezone, spend cap)                 |
| get_budget_info              |   Budget vs. daily spend with pacing status                       |
| get_pixel_events             |   Pixel configuration and event volumes                           |
| get_ad_creatives             |   Creative details (copy, images, CTAs)                           |
| get_creative_asset_details   |   Media library (images and videos with metadata)                 |

### Meta Ads — Write (24 tools)

| Tool                         |   Description                                                     |
|------------------------------|-------------------------------------------------------------------|
| pause_campaign               |   Pause a campaign                                                |
| enable_campaign              |   Enable a campaign                                               |
| pause_adset                  |   Pause an ad set                                                 |
| enable_adset                 |   Enable an ad set                                                |
| pause_ad                     |   Pause an ad                                                     |
| enable_ad                    |   Enable an ad                                                    |
| update_campaign_budget       |   Update campaign budget (daily or lifetime)                      |
| update_adset_budget          |   Update ad set budget                                            |
| update_ad_creative           |   Update ad copy (primary text, headline, description, CTA)       |
| update_ad_url                |   Update ad destination URL                                       |
| update_ad_utm                |   Update UTM tracking parameters                                  |
| update_ad_name               |   Rename an ad                                                    |
| create_campaign              |   Create a new campaign                                           |
| create_adset                 |   Create a new ad set with targeting and budget                   |
| create_ad                    |   Create a new ad with auto-detected page and creative            |
| duplicate_ad                 |   Duplicate an existing ad                                        |
| duplicate_adset              |   Duplicate an existing ad set                                    |
| update_adset_targeting       |   Update ad set audience targeting                                |
| update_adset_placements      |   Update ad set placement configuration                           |
| update_adset_schedule        |   Update ad set start and end dates                               |
| update_adset_bid             |   Update ad set bid strategy and amount                           |
| upload_image                 |   Upload an image for use in ad creatives                         |
| create_custom_audience       |   Create a custom audience                                        |
| create_lookalike_audience    |   Create a lookalike audience                                     |

## Prerequisites

### Google Ads

- A Google Ads MCC (Manager) account with access to client accounts
- A Google Cloud project with the Google Ads API enabled
- An OAuth 2.0 Client ID (Desktop type)
- A Developer Token (Basic or Standard access)
- A refresh token generated via the Google Ads OAuth flow

### Meta Ads

- A Meta Business Manager with access to client ad accounts
- A Meta Developer App
- An OAuth User Token with the following scopes: `ads_management`, `ads_read`, `business_management`, `pages_manage_ads`, `pages_read_engagement`
- The token must be converted to a long-lived token (60-day expiry)

Note: A System User token can be used for read operations and campaign/ad set management, but creating or modifying ads requires an OAuth User Token due to Meta's page permission model.

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/TheoCtla/AdOps-MCP.git
cd mcp
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env.example` to `.env` and fill in the required values:

```bash
cp .env.example .env
```

### 5. Run the server (stdio, local development)

```bash
python -m google_ads.server
```

### 6. Connect to Claude Code

```bash
claude mcp add tarmaac-mcp -- venv/bin/python -m google_ads.server
```

### 7. Connect via MCP Inspector (for testing)

```bash
npx @modelcontextprotocol/inspector
```

In the Inspector UI, set:
- Command: `venv/bin/python`
- Arguments: `-m google_ads.server`

## Project Structure

```
adops-mcp/
├── google_ads/
│   ├── auth.py                 # Google Ads client initialization
│   ├── formatting.py           # micros_to_euros, safe_ratio, date helpers
│   ├── helpers.py              # Error formatting, enum parsing, utilities
│   ├── queries.py              # GAQL query constants
│   ├── server.py               # MCP server entry point
│   └── tools/
│       ├── __init__.py         # Tool registration
│       ├── read/               # 24 read tools (1 file per tool)
│       └── write/              # 26 write tools (1 file per tool)
├── meta_ads/
│   ├── auth.py                 # Meta API initialization
│   ├── helpers.py              # Error formatting, currency conversion, action parsing
│   └── tools/
│       ├── __init__.py         # Tool registration
│       ├── read/               # 14 read tools (1 file per tool)
│       └── write/              # 24 write tools (1 file per tool)
├── .env.example
├── .gitignore
├── CLAUDE.md                   # Development rules for Claude Code
├── README.md
└── requirements.txt
```

Each tool is a single Python file exposing three attributes: `TOOL_NAME` (string), `TOOL_DEFINITION` (MCP Tool object), and `handler` (async function). Tools are registered via a centralized registry pattern.

## Currency Handling

- Google Ads returns monetary values in micros (1 EUR = 1,000,000 micros). All values are converted to euros before being returned.
- Meta Ads returns spend values in real currency (no conversion needed). Budgets are in cents (100 = 1 EUR) and are converted automatically.

## Error Handling

All tools return structured JSON responses. Errors include actionable messages in French with the original API error appended for debugging:

```json
{
  "error": "Pas d'acces au compte 5879788031. Verifiez les acces dans le MCC. [Google: Authorization error details]"
}
```

Common error scenarios (token expiry, rate limits, permission issues, invalid parameters) are handled gracefully without crashing the server.

## Authentication Notes

### Google Ads

The refresh token does not expire as long as the Google Cloud project remains active and the user does not revoke access. No regular renewal is needed.

### Meta Ads

The OAuth User Token expires after 60 days. To renew:

1. Go to https://developers.facebook.com/tools/explorer/
2. Select the app and request the required permissions
3. Generate a new short-lived token
4. Convert to long-lived using:

```bash
curl -i -X GET "https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=YOUR_APP_ID&client_secret=YOUR_APP_SECRET&fb_exchange_token=SHORT_LIVED_TOKEN"
```

5. Update `META_ACCESS_TOKEN` in `.env`
6. Restart the server

## Production Deployment

For production use on a VPS:

- Ubuntu 24.04 LTS recommended (Hetzner CX22 or equivalent)
- Caddy as reverse proxy for automatic HTTPS
- systemd services for process management
- Separate the server into two HTTP instances (one per platform) on different ports

See MAINTENANCE.md for operational procedures.

## Known Limitations

- Google Ads Auction Insights: requires specific API access that may not be available on all Developer Tokens, even with Standard access level.
- Meta Ads ad creation: requires an OAuth User Token (System User tokens lack page permissions for client accounts). The token must be renewed every 60 days.
- Meta Ads ad creation auto-detects the Facebook Page from existing ads on the account. Accounts with no existing ads require the page_id to be passed explicitly.

## License

This project is proprietary software developed for Tarmaac digital agency.