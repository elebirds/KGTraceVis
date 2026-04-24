# KG Construction

KG construction is source-constrained.

Candidate entities and triples may come from dataset labels, official tables,
curated project notes, SOP excerpts, or LLM-assisted extraction from provided
sources. LLM output is never treated as ground truth by default.

Each edge must keep its source, evidence text or row, confidence, weight, and
review status.
