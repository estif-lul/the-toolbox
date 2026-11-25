# The Toolbox: one command builds the film from storyboard.json.
# Every target is a thin wrapper around `uv run python -m pipeline.run <command>`, which also
# works without Make. Recipes run in sh (Git Bash on Windows).
#
#   make film                  the whole pipeline (cache hits for everything unchanged)
#   make film PROFILE=paid     the paid / frontier lane (config/providers.yaml)
#   make narration ONLY=s05    one stage, one shot
#   make keyframes FORCE=1     regenerate regardless of cache

RUN     := uv run python -m pipeline.run
FLAGS   := $(if $(PROFILE),--profile $(PROFILE),) $(if $(ONLY),--only $(ONLY),) $(if $(DRY_RUN),--dry-run,)
export FORCE RUN_GPU

.DEFAULT_GOAL := help
.PHONY: help setup smoke models validate test check secrets \
        script narration narration-check audition radio refs choose revise keyframes kenburns rough shots shots-push shots-pull music assemble film costs

help:                         ## list the targets
	@echo "The Toolbox pipeline. Targets:"
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/^([a-z-]+):.*## (.*)/  \1|\2/' | awk -F'|' '{printf "  %-14s %s\n", $$1, $$2}'
	@echo "Variables: PROFILE=free|paid  ONLY='s05 s06'  FORCE=1  DRY_RUN=1  RUN_GPU=1  ROLE= MODEL= VOICES= NO_STYLE=1"

setup:                        ## install Python 3.12 + deps (uv), install the secrets pre-commit hook
	uv sync
	uv run python scripts/check_secrets.py --install-hook

smoke:                        ## one minimal call per provider, latency logged to runs.jsonl
	$(RUN) smoke $(FLAGS)

models:                       ## list the models the API keys can see (verifies model ids)
	$(RUN) models $(FLAGS)

validate:                     ## JSON Schema + semantic checks of storyboard.json
	$(RUN) validate $(FLAGS)

test:                         ## unit tests (no network, no keys needed)
	uv run pytest

secrets:                      ## scan tracked files for API keys and tokens
	uv run python scripts/check_secrets.py

check: secrets test           ## secrets scan + tests + storyboard validation
	$(RUN) validate --if-present

script:                       ## [Step 1] Gemini draft of the storyboard -> storyboard.draft.json
	$(RUN) script $(FLAGS)

narration:                    ## [Step 2] TTS per line (cached) -> outputs/narration/timing.json
	$(RUN) narration $(FLAGS)

narration-check:              ## [Step 2] hear every line back (transcribe) + repair a wrong batch cut
	$(RUN) narration --verify $(FLAGS)

audition:                     ## [Step 2] candidate voices: make audition ROLE=dad [MODEL=...] [NO_STYLE=1]
	$(RUN) audition --role $(ROLE) $(if $(MODEL),--model $(MODEL),) $(if $(VOICES),--voices $(VOICES),) $(if $(NO_STYLE),--no-style,) $(FLAGS)

radio:                        ## [Step 2] radio cut: narration + placeholder music, subtitles
	$(RUN) radio $(FLAGS)

refs:                         ## [Step 3] style + character reference sheets
	$(RUN) refs $(FLAGS)

choose:                       ## [Step 3] record a pick: make choose ITEM=dad PICK=2 (style, dad, s05, s10a ...)
	$(RUN) choose $(ITEM) $(PICK)

revise:                       ## [Step 3] edit a chosen sheet: make revise ITEM=dad FROM=0 EDIT="remove the pencil"
	$(RUN) revise $(ITEM) $(FROM) "$(EDIT)" $(FLAGS)

keyframes:                    ## [Step 3] keyframe candidates per shot
	$(RUN) keyframes $(FLAGS)

kenburns:                     ## [Step 3] Ken Burns clip per shot
	$(RUN) kenburns $(FLAGS)

rough:                        ## [Step 3] rough film: Ken Burns stills + radio-cut sound, 9:16 and 16:9
	$(RUN) assemble --mode rough $(FLAGS)

shots:                        ## [Step 4] Wan 2.2 on Kaggle: push + wait + pull
	$(RUN) shots $(FLAGS)

shots-push:                   ## [Step 4] push stale Wan jobs to Kaggle (overnight runs)
	$(RUN) shots --push $(FLAGS)

shots-pull:                   ## [Step 4] pull finished Wan clips from Kaggle
	$(RUN) shots --pull $(FLAGS)

music:                        ## [Step 4] ACE-Step candidates + audition
	$(RUN) music $(FLAGS)

assemble:                     ## [Step 5] final edit, both aspect ratios
	$(RUN) assemble $(FLAGS)

film:                         ## [Step 5] the whole pipeline end to end
	$(RUN) film $(FLAGS)

costs:                        ## [Step 6] COSTS.md tables from runs.jsonl
	$(RUN) costs $(FLAGS)
