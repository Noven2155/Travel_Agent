"""Travel Agent (BIU DS23, team 8): shared foundation, tools, checks and three planning systems.

A = deterministic rules baseline (no LLM), B = single CrewAI agent with all tools,
C = CrewAI multi-agent (Trip Manager, Places, Itinerary). All three share the same
TripRequest input, deterministic tools over local files, code checks and RunResult output.
"""
__version__ = "0.1.0"
