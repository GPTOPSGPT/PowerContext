---
name: nearby-amap-recommendations
description: Recommend nearby places using Amap place search and walking routes.
---

# 周边去哪儿

When the user gives a city, origin and a nearby-place request, use the configured Amap MCP tools to recommend up to three independent walking destinations.

1. Parse the requested place type, any preferences, maximum walking time and requested count. Default to at most three. Use the supplied origin coordinate; resolve a textual origin with Amap only if necessary. Keep the city constraint.
2. Search Amap for relevant POIs near the origin. Search additional relevant categories or pages if the first set is insufficient. Keep the Amap POI name, address, coordinate and ID; do not invent candidates.
3. For each plausible candidate, call Amap walking route planning **from the same origin** to that candidate. Use the returned walking duration and distance, never straight-line distance, as the eligibility test. Exclude routes that fail or exceed the user's maximum time. Recheck a candidate if its search coordinate and route endpoint disagree materially.
4. Rank eligible places by the user's expressed preferences, then walking duration and distance. Return no more than the requested count and never more than three. Each result must be a distinct destination.
5. Answer in a concise list or table with place name, address, walking distance, walking time and one grounded recommendation reason. Say that each route starts from the origin. If too few places qualify, state how many were found; if no search/route data is available, explain the failure and suggest broadening the request. Mark quietness, queue length, current opening status and similar unverified claims as “未核实”.

Do not substitute guessed POIs or walking times when a tool fails. Do not chain the destinations into a multi-stop itinerary.
