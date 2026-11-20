# Overview

FINOS Workspace's dashboards on this deployment, read-only. The plugin serves
Workspace's front end on its own page and answers its widgets from the lake
and the instrument master, through its sidecar, at its entitlements, for the
person who opened the page.

## What it reads

- The latest reference rates in the lake, the euro's cash instrument priced
  in each currency, with each rate's business date, time and dataset.
- Each dataset it may read, whether it is entitled to it, and when its source
  was last heard.
- An instrument in the deployment's master, by an identifier.

## What it does not do

- It records nothing, and keeps nothing: no database, no saved dashboard. A
  person's changes to a dashboard last while their page is open.
- It has no sign-in, admin area or sharing of its own: the deployment signs
  people in and holds their access.
- It has no agent, copilot or MCP surface.
- It calls no address outside the deployment.
