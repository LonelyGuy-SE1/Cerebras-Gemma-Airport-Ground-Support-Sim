# 60-Second Recording Script

0-5s: Open the app and show both MuJoCo twins initialized from the same seeded runway/apron model with NASA aircraft visible.

5-10s: Click **Run 60s Demo**. Ground vehicles and aircraft begin moving in the 3D runway scene.

10-20s: The runway incursion triggers: DC-8 short final, crossing traffic on the active runway, G-III departure queue, and fuel hazard pressure. Both panes capture a rendered WebGL frame and MuJoCo telemetry while the world continues moving.

20-35s: The right pane receives the fast coordination policy, issues the go-around, locks the crossing, holds the departure queue, and freezes fuel traffic. The left pane applies a stale policy and shows elevated runway risk, policy staleness, and deadlock duration.

35-50s: Show live metrics: latency, policy staleness, runway risk, aircraft delay, conflicts avoided, deadlock duration, and challenge load.

50-60s: End on the reflex-window result card showing the latency gap, validity-window consumption, runway risk, and aircraft delay.
