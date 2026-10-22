# Travel comparison workspace

<!-- impeccable:product-schema 1 -->

## Platform
web

## Users
Galit and her four-person capstone team; a course presentation audience.

## Product Purpose
Submit one shared group-trip request and inspect three independently executed systems: deterministic code, one agent, three agents. Show package, itinerary, compromises and measured evaluation data.

## Capabilities and Constraints
Two weeks, Chicago/New York, historical flight catalog and simulated availability. No actual booking or payment. The same catalog and validation rules apply to all systems. At least four travelers in demonstration requests. Model execution must be distinguished from estimates and replay. Missing model configuration must be visible.

## Brand Commitments
The user selected the open white React interface with narrow right navigation, navy typography and restrained blue, stored at ../tourism_react_studio/design/selected-direction.png. Preserve that visual language; avoid dense generic AI dashboards.

## Evidence on Hand
Existing Python baseline and CrewAI implementations; data/inventory.json and data/places; supervisor feedback and updated Hebrew specification.

## Product Principles
- A single request, three comparable results.
- Facts come from the catalog and tool logs.
- Explicitly label estimates, unknowns, and unavailable model execution.
- Keep detail behind disclosures; the primary task stays visible.
