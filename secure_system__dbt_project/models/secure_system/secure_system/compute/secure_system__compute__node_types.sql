{{ config(
     alias='node_types'    
)}}


SELECT  
  -- account_id,
  node_type, 
  core_count, 
  memory_mb, 
  gpu_count 
from {{source('compute', 'node_types')}} sys
