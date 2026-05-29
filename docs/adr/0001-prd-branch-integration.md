# Integrate implementation branches through PRD branches

Each PRD Issue gets a PRD branch, and each child Implementation Issue gets its own branch created from that PRD branch. Agent Runs complete work on implementation branches and merge successful work back into the PRD branch automatically; humans review and merge the PRD branch to the main branch. This keeps autonomous work isolated per issue while giving humans one feature-level integration point instead of reviewing every child branch independently.
