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


GEO_PERFORMANCE_QUERY = """
    SELECT
      geographic_view.country_criterion_id,
      geographic_view.location_type,
      campaign.id,
      campaign.name,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.conversions_value
    FROM geographic_view
    WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
      {extra_where}
    ORDER BY metrics.cost_micros DESC
    LIMIT 100
"""


DEVICE_PERFORMANCE_QUERY = """
    SELECT
      segments.device,
      campaign.id,
      campaign.name,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.conversions_value
    FROM campaign
    WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
      AND campaign.status = 'ENABLED'
      {extra_where}
"""


AGE_PERFORMANCE_QUERY = """
    SELECT
      ad_group_criterion.age_range.type,
      ad_group.id,
      ad_group.name,
      campaign.id,
      campaign.name,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.conversions_value
    FROM age_range_view
    WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
      {extra_where}
"""


GENDER_PERFORMANCE_QUERY = """
    SELECT
      ad_group_criterion.gender.type,
      ad_group.id,
      ad_group.name,
      campaign.id,
      campaign.name,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.conversions_value
    FROM gender_view
    WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
      {extra_where}
"""


HOUR_OF_DAY_PERFORMANCE_QUERY = """
    SELECT
      segments.hour,
      campaign.id,
      campaign.name,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.conversions_value
    FROM campaign
    WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
      AND campaign.status = 'ENABLED'
      {extra_where}
    ORDER BY segments.hour ASC
"""


DAY_OF_WEEK_PERFORMANCE_QUERY = """
    SELECT
      segments.day_of_week,
      campaign.id,
      campaign.name,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.conversions_value
    FROM campaign
    WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
      AND campaign.status = 'ENABLED'
      {extra_where}
"""


EXTENSIONS_QUERY = """
    SELECT
      asset.id,
      asset.type,
      asset.name,
      asset.sitelink_asset.link_text,
      asset.sitelink_asset.description1,
      asset.sitelink_asset.description2,
      asset.final_urls,
      asset.callout_asset.callout_text,
      asset.structured_snippet_asset.header,
      asset.structured_snippet_asset.values,
      asset.image_asset.full_size.url,
      asset.price_asset.price_offerings
    FROM asset
    WHERE asset.type IN ('SITELINK', 'CALLOUT', 'STRUCTURED_SNIPPET',
      'IMAGE', 'PRICE', 'CALL')
      {extra_where}
"""


CAMPAIGN_EXTENSIONS_QUERY = """
    SELECT
      asset.id,
      asset.type,
      asset.name,
      asset.sitelink_asset.link_text,
      asset.sitelink_asset.description1,
      asset.sitelink_asset.description2,
      asset.final_urls,
      asset.callout_asset.callout_text,
      asset.structured_snippet_asset.header,
      asset.structured_snippet_asset.values,
      asset.image_asset.full_size.url,
      asset.price_asset.price_offerings,
      campaign.id,
      campaign.name
    FROM campaign_asset
    WHERE campaign.id = {campaign_id}
      AND asset.type IN ('SITELINK', 'CALLOUT', 'STRUCTURED_SNIPPET',
        'IMAGE', 'PRICE', 'CALL')
      {extra_where}
"""


CAMPAIGN_SETTINGS_QUERY = """
    SELECT
      campaign.id,
      campaign.name,
      campaign.status,
      campaign.advertising_channel_type,
      campaign.advertising_channel_sub_type,
      campaign.bidding_strategy_type,
      campaign.target_cpa.target_cpa_micros,
      campaign.target_roas.target_roas,
      campaign.network_settings.target_google_search,
      campaign.network_settings.target_search_network,
      campaign.network_settings.target_content_network,
      campaign.geo_target_type_setting.positive_geo_target_type,
      campaign.geo_target_type_setting.negative_geo_target_type,
      campaign_budget.amount_micros,
      campaign_budget.delivery_method,
      campaign_budget.type
    FROM campaign
    WHERE campaign.id = {campaign_id}
"""


AD_SCHEDULE_QUERY = """
    SELECT
      campaign_criterion.ad_schedule.day_of_week,
      campaign_criterion.ad_schedule.start_hour,
      campaign_criterion.ad_schedule.start_minute,
      campaign_criterion.ad_schedule.end_hour,
      campaign_criterion.ad_schedule.end_minute,
      campaign_criterion.bid_modifier,
      campaign.id,
      campaign.name
    FROM campaign_criterion
    WHERE campaign_criterion.type = 'AD_SCHEDULE'
      AND campaign.id = {campaign_id}
"""


BID_MODIFIERS_QUERY = """
    SELECT
      campaign_criterion.criterion_id,
      campaign_criterion.type,
      campaign_criterion.bid_modifier,
      campaign.id,
      campaign.name
    FROM campaign_criterion
    WHERE campaign_criterion.bid_modifier IS NOT NULL
      AND campaign.id = {campaign_id}
"""


LABELS_QUERY = """
    SELECT
      label.id,
      label.name,
      label.text_label.description
    FROM label
"""


CONVERSION_ACTIONS_QUERY = """
    SELECT
      conversion_action.id,
      conversion_action.name,
      conversion_action.type,
      conversion_action.status,
      conversion_action.category,
      conversion_action.counting_type,
      conversion_action.attribution_model_settings.attribution_model
    FROM conversion_action
    WHERE conversion_action.status = '{status}'
"""


AUCTION_INSIGHTS_QUERY = """
    SELECT
      segments.auction_insight_domain,
      metrics.auction_insight_search_impression_share,
      metrics.auction_insight_search_overlap_rate,
      metrics.auction_insight_search_position_above_rate,
      metrics.auction_insight_search_top_impression_percentage,
      metrics.auction_insight_search_absolute_top_impression_percentage,
      metrics.auction_insight_search_outranking_share
    FROM campaign
    WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
      AND campaign.id = {campaign_id}
"""


LANDING_PAGE_PERFORMANCE_QUERY = """
    SELECT
      landing_page_view.unexpanded_final_url,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.conversions_value,
      metrics.speed_score
    FROM landing_page_view
    WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
      {extra_where}
    ORDER BY metrics.clicks DESC
    LIMIT {limit}
"""


AUDIENCES_QUERY = """
    SELECT
      campaign_criterion.user_list.user_list,
      campaign_criterion.type,
      campaign_criterion.bid_modifier,
      campaign.id,
      campaign.name,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.conversions_value
    FROM campaign_audience_view
    WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
      {extra_where}
    ORDER BY metrics.cost_micros DESC
"""


CHANGE_HISTORY_QUERY = """
    SELECT
      change_event.change_date_time,
      change_event.user_email,
      change_event.change_resource_type,
      change_event.change_resource_name,
      change_event.changed_fields,
      change_event.client_type,
      change_event.resource_change_operation
    FROM change_event
    WHERE change_event.change_date_time BETWEEN '{date_from}' AND '{date_to}'
    ORDER BY change_event.change_date_time DESC
    LIMIT {limit}
"""


BUDGET_INFO_QUERY = """
    SELECT
      campaign.id,
      campaign.name,
      campaign.status,
      campaign_budget.amount_micros,
      campaign_budget.type,
      metrics.cost_micros
    FROM campaign
    WHERE campaign.status = 'ENABLED'
      AND segments.date = '{today}'
"""
