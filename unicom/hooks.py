app_name = "unicom"
app_title = "UniCom"
app_publisher = "UniVentures"
app_description = "Issue coordination"
app_email = "support@univenturescloud.com"
app_license = "MIT"

permission_query_conditions = {"UniCom Issue": "unicom.permissions.issue_query"}
has_permission = {"UniCom Issue": "unicom.permissions.issue_permission"}
website_route_rules = [{"from_route": "/unicom/<path:app_path>", "to_route": "unicom"}]
