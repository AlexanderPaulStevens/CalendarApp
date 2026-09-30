.PHONY: help install test api ui up down

help install test api ui up down:
	$(MAKE) -C backend $@
