{{ config(
     alias='list_prices'    
)}}


SELECT  
--   account_id,
  price_start_time,
  price_end_time,
  sku_name,
  cloud,
  currency_code,
  usage_unit,
  pricing
FROM {{source('billing', 'list_prices')}} sys
