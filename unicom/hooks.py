app_name = "unicom"
app_title = "UniCom"
app_publisher = "UniVentures"
app_description = "Issue coordination"
app_email = "support@univenturescloud.com"
app_license = "MIT"

permission_query_conditions = {"UniCom Issue": "unicom.permissions.issue_query"}
has_permission = {"UniCom Issue": "unicom.permissions.issue_permission"}
website_route_rules = [{"from_route": "/unicom/<path:app_path>", "to_route": "unicom"}]

# Desk integration uses the same permission-filtered issue API as the app.
app_include_js = ['/assets/unicom/js/desk.js?v=optional-action-1']
app_include_css = ['/assets/unicom/css/desk.css?v=4effa3f']
add_to_apps_screen = [{'name': 'unicom', 'title': 'UniCom', 'route': '/unicom', 'logo': '/assets/unicom/images/desk-chat.svg'}]
