# Makefile
#
# Builds the Pokemon HeartGold .apworld. Requires `python` on PATH.
# On Windows without `make`, use `python build.py` directly instead (see
# build.py — same packaging logic, pure Python, no extra tooling required).

.PHONY: default clean

default:
	@python build.py

clean:
	@rm -f *.apworld
