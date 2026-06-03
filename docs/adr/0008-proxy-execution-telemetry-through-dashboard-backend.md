# Proxy execution telemetry through dashboard backend

The Orchestration Control Center reads Execution Telemetry from the external pi-agent-observability service, but the React dashboard consumes telemetry through the Rangkai dashboard backend instead of connecting to pi-agent-observability directly. Rangkai remains the source of truth for PRD Issue, Implementation Issue, and Agent Run lifecycle state, while pi-agent-observability remains the source of truth for Telemetry Sessions; the backend joins them through explicit Run Telemetry Associations and returns dashboard-shaped metrics. This replaces the earlier database-driven telemetry recommendation so observability credentials, raw event shapes, and cross-service normalization stay out of the browser.

Telemetry is exposed to the dashboard as an initial snapshot plus live Server-Sent Event updates. The snapshot makes historical metrics visible immediately after page load, while the SSE stream keeps active Agent Run metrics current without making live-only delivery the source of truth.

Rangkai computes dashboard metrics on demand for v1 instead of storing derived metrics in its own database. A local metrics store is deferred until there is measured need for query caching, retention independent of pi-agent-observability, or historical metric snapshots.
