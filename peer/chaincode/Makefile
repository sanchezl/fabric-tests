
.PHONY: test test-with-java

help:
	@printf "\n"\
	"Run all scenarios (only use golang chaincode):\n"\
	"  behave\n\n"\
	"Options:\n"\
	"  --define java-cc-enabled  Also use Java chaincode.\n"\
	"  --define save-logs        Save container logs.\n"\
	"  --define do-not-decompose Save docker containers.\n"\
	"  --stop                    Stop on first failure.\n\n"

test:
	@behave

test-with-java:
	@behave --define java-cc-enabled

.PHONY: clean
clean:
	@$(RM) *.log
