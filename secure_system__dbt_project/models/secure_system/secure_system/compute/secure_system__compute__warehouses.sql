{{ config(
     alias='warehouses'    
)}}

WITH workspace_admins AS (
    SELECT 
        workspace_id, 
        workspace_name, 
        workspace_url, 
        admin_email,
        ROW_NUMBER() OVER (PARTITION BY workspace_id ORDER BY admin_email) AS admin_rank
    FROM (
        {{ref('workspace_owners')}}
    ) admins
)
SELECT 
    wa.admin_email,
    sys.*
FROM {{source('compute', 'warehouses')}} sys
LEFT JOIN workspace_admins wa
ON sys.workspace_id = wa.workspace_id
WHERE wa.admin_email = current_user();