# Maintaining the UM charging study

Keep the port–warehouse experiments anchored to a fixed transport service, truck battery limits, site connection capacity, connector counts and charging windows. The principal comparison is the investment and operating cost of completing the same service. Keep observed timestamps, inferred parking bounds and assumed charging eligibility distinct.

Use a small runnable case to explain a change in a planning decision. Give units, state the cost horizon and tie each result to its inputs. Update both languages in the main README when the headline case changes. Cite methods and data where they are used. Record material research decisions, including negative findings, in the existing study records.

The Fresia replication lives under studies/fresia-2025/. Label results obtained using substitute data or fixed UM routes. The planned electricity-market study starts with fixed facilities and historical day-ahead purchasing prices. Record the market area, dates, timezone, price units and what the operator knows when scheduling.

GitHub holds research code, data with provenance and appropriate sharing rights, testable examples, methods and selected results. Preserve detailed run logs, personal documents, prompts and working conversations in the existing offline Git archive. Check staged paths before pushing. When reviewing with Claude, attribute only reviews that actually ran. Use research branch names such as research/investment-milp-YYYYMMDD. Publish validated milestones to main when authorized and verify the remote commit.
