"""Requêtes GAQL utilisées par les tools MCP."""

# Le statut est interpolé par le handler après validation contre un enum
# (pas d'injection GAQL possible, la valeur est whitelistée côté Python).
LIST_ACCOUNTS_QUERY = """
    SELECT
      customer_client.client_customer,
      customer_client.descriptive_name,
      customer_client.status,
      customer_client.currency_code,
      customer_client.time_zone,
      customer_client.manager
    FROM customer_client
    WHERE customer_client.status = '{status}'
"""


# ``{extra_where}`` est concaténé côté Python à partir de fragments déjà
# validés / échappés (statuts whitelistés, IDs numériques, chaînes GAQL
# échappées avec ``'' ``) pour éviter l'injection GAQL.
CAMPAIGN_PERFORMANCE_QUERY = """
    SELECT
      campaign.id,
      campaign.name,
      campaign.advertising_channel_type,
      campaign.status,
      campaign.bidding_strategy_type,
      campaign_budget.amount_micros,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.conversions_value,
      metrics.ctr,
      metrics.average_cpc,
      metrics.cost_per_conversion,
      metrics.search_impression_share
    FROM campaign
    WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
      AND campaign.status = '{status}'
      {extra_where}
    ORDER BY metrics.cost_micros DESC
"""


ADGROUP_PERFORMANCE_QUERY = """
    SELECT
      ad_group.id,
      ad_group.name,
      ad_group.type,
      ad_group.status,
      ad_group.cpc_bid_micros,
      campaign.id,
      campaign.name,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.conversions_value,
      metrics.ctr,
      metrics.average_cpc,
      metrics.cost_per_conversion
    FROM ad_group
    WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
      AND ad_group.status = '{status}'
      {extra_where}
    ORDER BY metrics.cost_micros DESC
"""


KEYWORDS_QUERY = """
    SELECT
      ad_group_criterion.criterion_id,
      ad_group_criterion.keyword.text,
      ad_group_criterion.keyword.match_type,
      ad_group_criterion.status,
      ad_group_criterion.quality_info.quality_score,
      ad_group_criterion.quality_info.creative_quality_score,
      ad_group_criterion.quality_info.post_click_quality_score,
      ad_group_criterion.quality_info.search_predicted_ctr,
      ad_group.id,
      ad_group.name,
      campaign.id,
      campaign.name,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.ctr,
      metrics.average_cpc,
      metrics.cost_per_conversion
    FROM keyword_view
    WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
      AND ad_group_criterion.status = '{status}'
      {extra_where}
    ORDER BY metrics.cost_micros DESC
"""


DAILY_PERFORMANCE_QUERY = """
    SELECT
      segments.date,
      campaign.id,
      campaign.name,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.conversions_value,
      metrics.ctr,
      metrics.average_cpc,
      metrics.cost_per_conversion
    FROM campaign
    WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
      AND campaign.status = 'ENABLED'
      {extra_where}
    ORDER BY segments.date ASC, campaign.name ASC
"""


SEARCH_TERMS_QUERY = """
    SELECT
      search_term_view.search_term,
      search_term_view.status,
      segments.keyword.info.text,
      segments.keyword.info.match_type,
      campaign.id,
      campaign.name,
      ad_group.id,
      ad_group.name,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.conversions_value
    FROM search_term_view
    WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
      {extra_where}
    ORDER BY metrics.cost_micros DESC
    LIMIT {limit}
"""


NEGATIVE_KEYWORDS_CAMPAIGN_QUERY = """
    SELECT
      campaign_criterion.criterion_id,
      campaign_criterion.keyword.text,
      campaign_criterion.keyword.match_type,
      campaign.id,
      campaign.name
    FROM campaign_criterion
    WHERE campaign_criterion.type = 'KEYWORD'
      AND campaign_criterion.negative = TRUE
      {extra_where}
"""


NEGATIVE_KEYWORDS_ADGROUP_QUERY = """
    SELECT
      ad_group_criterion.criterion_id,
      ad_group_criterion.keyword.text,
      ad_group_criterion.keyword.match_type,
      ad_group.id,
      ad_group.name,
      campaign.id,
      campaign.name
    FROM ad_group_criterion
    WHERE ad_group_criterion.negative = TRUE
      AND ad_group_criterion.type = 'KEYWORD'
      {extra_where}
"""


ADS_QUERY = """
    SELECT
      ad_group_ad.ad.id,
      ad_group_ad.ad.type,
      ad_group_ad.ad.final_urls,
      ad_group_ad.ad.responsive_search_ad.headlines,
      ad_group_ad.ad.responsive_search_ad.descriptions,
      ad_group_ad.ad.responsive_search_ad.path1,
      ad_group_ad.ad.responsive_search_ad.path2,
      ad_group_ad.ad.expanded_text_ad.headline_part1,
      ad_group_ad.ad.expanded_text_ad.headline_part2,
      ad_group_ad.ad.expanded_text_ad.headline_part3,
      ad_group_ad.ad.expanded_text_ad.description,
      ad_group_ad.ad.expanded_text_ad.description2,
      ad_group_ad.ad.expanded_text_ad.path1,
      ad_group_ad.ad.expanded_text_ad.path2,
      ad_group_ad.ad_strength,
      ad_group_ad.status,
      ad_group.id,
      ad_group.name,
      campaign.id,
      campaign.name,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.conversions_value
    FROM ad_group_ad
    WHERE ad_group_ad.status = '{status}'
      AND segments.date BETWEEN '{date_from}' AND '{date_to}'
      {extra_where}
    ORDER BY metrics.impressions DESC
"""
