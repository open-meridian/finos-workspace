"""FINOS Workspace's front end as an Open Meridian `reporting` plugin.

The wrapper serves the front end on the plugin's page, answers the part of
Workspace's `/app` API the front end calls (session, dashboards, the one
built-in connection and its widget requests), and answers each widget in
process from the lake and the master, through the plugin's sidecar, for the
person the page's request names. It keeps nothing: no database, no account,
no saved dashboard.
"""
