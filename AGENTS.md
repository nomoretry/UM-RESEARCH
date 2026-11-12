# Maintaining the UM charging study

Keep the port–warehouse experiments anchored to a fixed transport service, truck battery limits, site connection capacity, connector counts and charging windows. The principal comparison is the investment and operating cost of completing the same service. Keep observed timestamps, inferred parking bounds and assumed charging eligibility distinct.

Use a small runnable case to explain a change in a planning decision. Give units, state the cost horizon and tie each result to its inputs. Update both languages in the main README when the headline case changes. Cite methods and data where they are used. Record material research decisions, including negative findings, in the existing study records.

The Fresia replication lives under studies/fresia-2025/. Label results obtained using substitute data or fixed UM routes. Settle fixed-facility dispatch with the native historical day-ahead intervals. Record the market area, dates, timezone, price units and what the operator knows when scheduling.

Keep the bilingual homepage focused on the facility decision. Change a headline when evidence changes that decision; keep schedules and run history in the case. Trace each result from credited inputs and scenario assumptions to one command, its expected number and the results file. Run that path from the repository root and check links on the branch where readers will open them.

GitHub holds research code, data with provenance and appropriate sharing rights, testable examples, methods and selected results. Preserve detailed run logs, personal documents, prompts and working conversations in the existing offline Git archive. Check staged paths before pushing. When reviewing with Claude, attribute only reviews that actually ran. Use research branch names such as research/investment-milp-YYYYMMDD. Publish validated milestones to main when authorized and verify the remote commit.
