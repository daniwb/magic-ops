# Production Goose completion ceiling raised to 32,000

Authorized by Dani on 2026-09-20. Updated the production adapter MAX_TOKENS, profile declaration and worker description from 16,000 to 32,000. Thinking remains enabled. This is the combined reasoning-and-answer completion budget supported by Halogen.

The next model-call process reads the new value automatically; the controller does not need restarting. Already-running requests retain their original budget. No active request was interrupted.

Validation: six adapter tests passed, including accepting a complete 24,000-token response and rejecting an unfinished/32,000-token response; all five enabled profiles/baseline passed validation. Real installed Goose against a deterministic mock endpoint sent exactly one OpenAI-compatible request with max_tokens=32000, no tools, the complete packet and correct output telemetry (production-adapter-wire-check.json). Server health is retained separately. This confirms the request configuration, not an improved real-ticket success rate.

Repair allowance, evidence discovery, timeouts and all gates are unchanged in this step. No historical benchmark results were rewritten.
