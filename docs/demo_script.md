# 60-Second Recording Script

0-5s: "Both panes start from the same seeded airport state. Every ground vehicle has a mission: fuel, bags, catering, bus, pushback, and security."

5-10s: Click **Run 60s Demo**. "A runway incursion hits: a DC-8 is short final, a cargo aircraft is crossing the active runway, and a departure aircraft is held at runway 27."

10-20s: "Both coordinators receive the same rendered frame plus live vectors: heading, speed, target, clearance, and risk. The world keeps moving while they think."

20-35s: "Cerebras Gemma returns first. It issues go-around, crossing lockout, departure hold, and fuel freeze while the policy is still synchronized with the scene."

35-50s: "The slow baseline applies late. The runway state has already changed, so its policy consumes more of the validity window and scores higher runway risk."

50-60s: "The comparison is the product: fast inference keeps semantic coordination connected to physical reality."
